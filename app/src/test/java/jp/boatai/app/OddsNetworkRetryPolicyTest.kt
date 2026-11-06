package jp.boatai.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.SocketTimeoutException
import java.net.UnknownHostException

class OddsNetworkRetryPolicyTest {
    @Test
    fun wrappedDnsFailureSkipsRepeatedRequestsToIdenticalHost() {
        val root = IllegalStateException("Official page unavailable", UnknownHostException("www.boatrace.jp"))
        assertTrue(OddsNetworkRetryPolicy.isDnsFailure(root))
    }

    @Test
    fun timeoutIsNotMistakenForDnsFailure() {
        assertFalse(OddsNetworkRetryPolicy.isDnsFailure(SocketTimeoutException("temporary read timeout")))
    }
}
