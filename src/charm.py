#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module defining the Charmed operator for the FINOS Legend Studio."""

import json
import logging
import traceback

from charms.finos_legend_libs.v0 import legend_operator_base
from ops import charm, main, model

logger = logging.getLogger(__name__)

STUDIO_SERVICE_NAME = "studio"
STUDIO_CONTAINER_NAME = "studio"
LEGEND_DB_RELATION_NAME = "legend-db"
LEGEND_GITLAB_RELATION_NAME = "legend-studio-gitlab"
SDLC_RELATION_NAME = "legend-sdlc"
ENGINE_RELATION_NAME = "legend-engine"


APPLICATION_SERVER_UI_PATH = "/studio"
STUDIO_SERVICE_URL_FORMAT = "%(schema)s://%(host)s%(path)s"
STUDIO_GITLAB_REDIRECT_URI_FORMAT = "%(base_url)s/log.in/callback"
STUDIO_UI_CONFIG_FILE_CONTAINER_LOCAL_PATH = "/ui-config.json"
STUDIO_HTTP_CONFIG_FILE_CONTAINER_LOCAL_PATH = "/http-config.json"

TRUSTSTORE_PASSPHRASE = "Legend Studio"
TRUSTSTORE_CONTAINER_LOCAL_PATH = "/truststore.jks"

APPLICATION_CONNECTOR_PORT_HTTP = 8080
APPLICATION_CONNECTOR_PORT_HTTPS = 8081

GITLAB_REQUIRED_SCOPES = ["openid", "profile", "api"]


class LegendStudioCharm(legend_operator_base.BaseFinosLegendCoreServiceCharm):
    """Charmed operator for the FINOS Legend Studio Server."""

    def __init__(self, *args):
        super().__init__(*args)

        # SDLC relation events:
        self.framework.observe(
            self.on[SDLC_RELATION_NAME].relation_joined, self._on_sdlc_relation_joined
        )
        self.framework.observe(
            self.on[SDLC_RELATION_NAME].relation_changed, self._on_sdlc_relation_changed
        )
        self.framework.observe(
            self.on[SDLC_RELATION_NAME].relation_broken, self._on_sdlc_relation_broken
        )

        # Engine relation events:
        self.framework.observe(
            self.on[ENGINE_RELATION_NAME].relation_joined, self._on_engine_relation_joined
        )
        self.framework.observe(
            self.on[ENGINE_RELATION_NAME].relation_changed, self._on_engine_relation_changed
        )
        self.framework.observe(
            self.on[ENGINE_RELATION_NAME].relation_broken, self._on_engine_relation_broken
        )

    @classmethod
    def _get_application_connector_port(cls):
        return APPLICATION_CONNECTOR_PORT_HTTP

    @classmethod
    def _get_workload_container_name(cls):
        return STUDIO_CONTAINER_NAME

    @classmethod
    def _get_workload_service_names(cls):
        return [STUDIO_SERVICE_NAME]

    @classmethod
    def _get_workload_pebble_layers(cls):
        return {
            "studio": {
                "summary": "Studio layer.",
                "description": "Pebble config layer for FINOS Legend Studio.",
                "services": {
                    "studio": {
                        "override": "replace",
                        "summary": "studio",
                        "command": (
                            # NOTE(aznashwan): starting through bash is needed
                            # for the classpath glob (-cp ...) to be expanded:
                            "/bin/sh -c 'java -XX:+ExitOnOutOfMemoryError "
                            "-Xss4M -XX:MaxRAMPercentage=60 "
                            "-Dfile.encoding=UTF8v "
                            '-Djavax.net.ssl.trustStore="%s" '
                            '-Djavax.net.ssl.trustStorePassword="%s" '
                            "-cp /app/bin/webapp-content:/app/bin/* "
                            "org.finos.legend.server.shared."
                            'staticserver.Server server "%s"\''
                            % (
                                TRUSTSTORE_CONTAINER_LOCAL_PATH,
                                TRUSTSTORE_PASSPHRASE,
                                STUDIO_HTTP_CONFIG_FILE_CONTAINER_LOCAL_PATH,
                            )
                        ),
                        # NOTE(aznashwan): considering the Studio service
                        # expects a singular config file which already contains
                        # all relevant options in it (some of which will
                        # require the relation with DB/GitLab to have already
                        # been established), we do not auto-start:
                        "startup": "disabled",
                        # TODO(aznashwan): determine any env vars we could pass
                        # (most notably, things like the RAM percentage etc...)
                        "environment": {},
                    }
                },
            }
        }

    def _get_jks_truststore_preferences(self):
        jks_prefs = {
            "truststore_path": TRUSTSTORE_CONTAINER_LOCAL_PATH,
            "truststore_passphrase": TRUSTSTORE_PASSPHRASE,
            "trusted_certificates": {},
        }
        cert = self._get_legend_gitlab_certificate()
        if cert:
            # NOTE(aznashwan): cert label 'gitlab-studio' is arbitrary:
            jks_prefs["trusted_certificates"]["gitlab-studio"] = cert
        return jks_prefs

    @classmethod
    def _get_legend_gitlab_relation_name(cls):
        return LEGEND_GITLAB_RELATION_NAME

    @classmethod
    def _get_legend_db_relation_name(cls):
        return LEGEND_DB_RELATION_NAME

    @classmethod
    def _get_required_relations(cls):
        # NOTE(aznashwan): the Studio cannot function without an SDLC/Engine:
        rels = [SDLC_RELATION_NAME, ENGINE_RELATION_NAME]
        rels.extend(super()._get_required_relations())
        return rels

    def _get_studio_service_url(self):
        svc_name = self.model.config["external-hostname"] or self.app.name
        return STUDIO_SERVICE_URL_FORMAT % (
            {
                # NOTE(aznashwan): we always return the plain HTTP endpoint:
                "schema": legend_operator_base.APPLICATION_CONNECTOR_TYPE_HTTP,
                "host": svc_name,
                "path": APPLICATION_SERVER_UI_PATH,
            }
        )

    def _get_legend_gitlab_redirect_uris(self):
        base_url = self._get_studio_service_url()
        redirect_uris = [STUDIO_GITLAB_REDIRECT_URI_FORMAT % {"base_url": base_url}]
        return redirect_uris

    def _get_legend_service_url_from_relaton(self, service_name):
        """Fetches the redirect URL for the given pre-related legend service.

        Given the name of a service, attempts to extract the
        'legend-$NAME-url' property from the 'legend-$NAME' relation.
        """
        relation_name = "legend-%s" % service_name
        legend_relations = [SDLC_RELATION_NAME, ENGINE_RELATION_NAME]
        if relation_name not in legend_relations:
            raise ValueError(
                "Unknown service relation '%s', must be one of: %s"
                % (relation_name, legend_relations)
            )

        rel = self._get_relation(relation_name)
        if not rel:
            return None

        return rel.data[rel.app].get("legend-%s-url" % service_name)

    def _get_core_legend_service_configs(self, legend_db_credentials, legend_gitlab_credentials):
        # Compile Legend services UI config:
        service_urls = {"sdlc": None, "engine": None}
        try:
            for service in service_urls:
                service_urls[service] = self._get_legend_service_url_from_relaton(service)
        except Exception:
            logger.error(
                "Exception occurred while getting Legend service URLs: %s", traceback.format_exc()
            )
            return model.BlockedStatus("error getting legend service URLs")
        missing = [svc for svc, url in service_urls.items() if not url]
        if missing:
            return model.WaitingStatus(
                "awaiting relations with following services: %s" % (", ".join(missing))
            )
        studio_ui_config = {
            "appName": "studio",
            "env": "test",
            "sdlc": {"url": service_urls["sdlc"]},
            "metadata": {"url": "__LEGEND_DEPOT_URL__/api"},
            "engine": {"url": service_urls["engine"]},
            "documentation": {"url": "https://legend.finos.org"},
            "options": {
                "core": {
                    # TODO(aznashwan): could this error in the future?
                    "TEMPORARY__disableServiceRegistration": True
                }
            },
        }

        # Check DB creds:
        if not legend_db_credentials:
            return model.WaitingStatus("no legend db info present in relation yet")
        legend_db_uri = legend_db_credentials["uri"]
        legend_db_name = legend_db_credentials["database"]

        # Check GitLab-related options:
        if not legend_gitlab_credentials:
            return model.WaitingStatus("no legend gitlab info present in relation yet")
        gitlab_client_id = legend_gitlab_credentials["client_id"]
        gitlab_client_secret = legend_gitlab_credentials["client_secret"]
        gitlab_openid_discovery_url = legend_gitlab_credentials["openid_discovery_url"]

        # Check Java logging options:
        pac4j_logging_level = self._get_logging_level_from_config("server-pac4j-logging-level")
        server_logging_level = self._get_logging_level_from_config("server-logging-level")
        if not all([server_logging_level, pac4j_logging_level]):
            return model.BlockedStatus(
                "one or more logging config options are improperly formatted "
                "or missing, please review the debug-log for more details"
            )

        # Compile base config:
        studio_http_config = {
            "uiPath": APPLICATION_SERVER_UI_PATH,
            "html5Router": True,
            "server": {
                "type": "simple",
                "applicationContextPath": "/",
                "adminContextPath": "%s/admin" % APPLICATION_SERVER_UI_PATH,
                "connector": {
                    "type": legend_operator_base.APPLICATION_CONNECTOR_TYPE_HTTP,
                    "port": APPLICATION_CONNECTOR_PORT_HTTP,
                },
            },
            "logging": {
                "level": server_logging_level,
                "loggers": {
                    "root": {"level": server_logging_level},
                    "org.pac4j": {"level": pac4j_logging_level},
                },
                "appenders": [{"type": "console"}],
            },
            "pac4j": {
                "callbackPrefix": "/studio/log.in",
                "bypassPaths": ["/studio/admin/healthcheck"],
                "mongoUri": legend_db_uri,
                "mongoDb": legend_db_name,
                "clients": [
                    {
                        "org.finos.legend.server.pac4j.gitlab.GitlabClient": {
                            "name": "gitlab",
                            "clientId": gitlab_client_id,
                            "secret": gitlab_client_secret,
                            "discoveryUri": gitlab_openid_discovery_url,
                            # NOTE(aznashwan): needs to be a space-separated str:
                            "scope": " ".join(GITLAB_REQUIRED_SCOPES),
                        }
                    }
                ],
                "mongoSession": {"enabled": True, "collection": "userSessions"},
            },
            # TODO(aznashwan): check if these are necessary:
            "routerExemptPaths": [
                "/editor.worker.js",
                "/json.worker.js",
                "/editor.worker.js.map",
                "/json.worker.js.map",
                "/version.json",
                "/config.json",
                "/favicon.ico",
                "/static",
            ],
            "localAssetPaths": {
                "/studio/config.json": (STUDIO_UI_CONFIG_FILE_CONTAINER_LOCAL_PATH)
            },
        }

        return {
            STUDIO_UI_CONFIG_FILE_CONTAINER_LOCAL_PATH: (json.dumps(studio_ui_config, indent=4)),
            STUDIO_HTTP_CONFIG_FILE_CONTAINER_LOCAL_PATH: (
                json.dumps(studio_http_config, indent=4)
            ),
        }

    def _on_sdlc_relation_joined(self, _: charm.RelationJoinedEvent):
        logger.debug("No actions are to be performed after SDLC relation join")

    def _on_sdlc_relation_changed(self, _: charm.RelationChangedEvent) -> None:
        self._refresh_charm_status()

    def _on_sdlc_relation_broken(self, _: charm.RelationBrokenEvent) -> None:
        self._refresh_charm_status()

    def _on_engine_relation_joined(self, _: charm.RelationJoinedEvent):
        logger.debug("No actions are to be performed after engine relation join")

    def _on_engine_relation_changed(self, _: charm.RelationChangedEvent) -> None:
        self._refresh_charm_status()

    def _on_engine_relation_broken(self, _: charm.RelationBrokenEvent) -> None:
        self._refresh_charm_status()


if __name__ == "__main__":
    main.main(LegendStudioCharm)
