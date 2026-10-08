import QtQuick
import QtTest
import "../../providers" as Providers

Item {
  Component {
    id: authFactory
    Providers.AuthManager {
      pluginDir: "/tmp/omamail-test"
      accountId: "alice@example.com"
    }
  }

  TestCase {
    name: "EvolutionRecovery"

    function brokerProcess(auth) {
      for (var i = 0; i < auth.children.length; i++) {
        var child = auth.children[i]
        if (child.command && String(child.command[0]).indexOf("evolution-token.py") >= 0)
          return child
      }
      return null
    }

    function unavailable(auth, raw) {
      auth.restoreSession()
      var broker = brokerProcess(auth)
      verify(broker !== null)
      broker.running = false
      auth.handleBrokerLookup(raw)
      compare(auth.loggedIn, false)
      compare(auth.sessionChecked, true)
      return broker
    }

    function test_unlock_recovers_without_oauth_client() {
      var auth = createTemporaryObject(authFactory, this)
      var broker = unavailable(auth, '{"retryable":true}')
      compare(auth.credentialsPresent, false)
      compare(auth.savedSessionPresent, false)
      compare(auth.refreshRetryAttempt, 1)
      tryCompare(broker, "running", true, 6500)
      broker.running = false
      auth.handleBrokerLookup('{"accessToken":"synthetic-token","expiresIn":3600}')
      compare(auth.loggedIn, true)
      compare(auth.systemBrokerRetryNeeded, false)
      compare(auth.refreshRetryAttempt, 0)
    }

    function test_missing_account_does_not_retry() {
      var auth = createTemporaryObject(authFactory, this)
      unavailable(auth, "")
      compare(auth.systemBrokerRetryNeeded, false)
      compare(auth.refreshRetryAttempt, 0)
    }

    function test_signout_cancels_recovery() {
      var auth = createTemporaryObject(authFactory, this)
      var broker = unavailable(auth, '{"retryable":true}')
      auth.logout()
      compare(auth.systemBrokerSuppressed, true)
      compare(auth.systemBrokerRetryNeeded, false)
      wait(5500)
      compare(broker.running, false)
      compare(auth.loggedIn, false)
    }
  }
}
