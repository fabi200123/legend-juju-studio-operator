# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module testing the Legend Studio Operator."""

import json

from charms.finos_legend_libs.v0 import legend_operator_testing
from ops import testing as ops_testing

import charm


class LegendStudioTestWrapper(charm.LegendStudioCharm):
    @classmethod
    def _get_relations_test_data(cls):
        return {
            cls._get_legend_db_relation_name(): {
                "legend-db-connection": json.dumps(
                    {
                        "username": "test_db_user",
                        "password": "test_db_pass",
                        "database": "test_db_name",
                        "uri": "test_db_uri",
                    }
                )
            },
            cls._get_legend_gitlab_relation_name(): {
                "legend-gitlab-connection": json.dumps(
                    {
                        "gitlab_host": "gitlab_test_host",
                        "gitlab_port": 7667,
                        "gitlab_scheme": "https",
                        "client_id": "test_client_id",
                        "client_secret": "test_client_secret",
                        "openid_discovery_url": "test_discovery_url",
                        "gitlab_host_cert_b64": "test_gitlab_cert",
                    }
                )
            },
            charm.SDLC_RELATION_NAME: {
                "legend-sdlc-url": "test_sdlc_url",
            },
            charm.ENGINE_RELATION_NAME: {
                "legend-engine-url": "test_engine_url",
            },
        }

    def _get_service_configs_clone(self, relation_data):
        return {}


class LegendStudioTestCase(legend_operator_testing.TestBaseFinosCoreServiceLegendCharm):
    @classmethod
    def _set_up_harness(cls):
        harness = ops_testing.Harness(LegendStudioTestWrapper)
        return harness

    def test_relations_waiting(self):
        self._test_relations_waiting()

    def test_config_changed_update_gitlab_relation(self):
        self._test_update_config_gitlab_relation()

    def test_update_config_gitlab_relation_without_being_leader(self):
        self._test_update_config_gitlab_relation_without_being_leader()

    def test_upgrade_charm(self):
        self._test_upgrade_charm()

    def test_get_studio_service_url(self):
        self.harness.set_leader(True)
        self.harness.begin_with_initial_hooks()

        # Test without external-hostname config.
        actual_url = self.harness.charm._get_studio_service_url()

        expected_url = "http://%s%s" % (
            self.harness.charm.app.name,
            charm.APPLICATION_SERVER_UI_PATH,
        )
        self.assertEqual(expected_url, actual_url)

        # Test with external-hostname config.
        hostname = "foo.lish"
        self.harness.update_config({"external-hostname": hostname})
        actual_url = self.harness.charm._get_studio_service_url()

        expected_url = "http://%s%s" % (hostname, charm.APPLICATION_SERVER_UI_PATH)
        self.assertEqual(expected_url, actual_url)

        # Test with enable-tls set.
        self.harness.update_config({"enable-tls": True})
        actual_url = self.harness.charm._get_studio_service_url()

        expected_url = "https://%s%s" % (hostname, charm.APPLICATION_SERVER_UI_PATH)
        self.assertEqual(expected_url, actual_url)
