package jp.boatai.app

import java.net.UnknownHostException

/** Distinguish a host-wide DNS outage from a short-lived individual HTTP error. */
internal object OddsNetworkRetryPolicy {
    fun isDnsFailure(error: Throwable): Boolean {
        var current: Throwable? = error
        val seen = mutableSetOf<Throwable>()
        while (current != null && seen.add(current)) {
            if (current is UnknownHostException) return true
            current = current.cause
        }
        return false
    }
}
