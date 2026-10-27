package jp.boatai.app

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class DataFetchAuditWindowTest {
    @Test
    fun latest48EventsAreKeptInOrderIncludingFailures() {
        var recent = JSONArray()
        for (n in 0 until 75) {
            val event = JSONObject().put("sequence", n)
                .put("status", if (n % 7 == 0) "ERROR" else "OK")
            recent = DataFetchAuditWindow.append(recent, event)
        }
        assertEquals(48, recent.length())
        assertEquals(27, recent.getJSONObject(0).getInt("sequence"))
        assertEquals(74, recent.getJSONObject(47).getInt("sequence"))
        assertEquals("ERROR", recent.getJSONObject(29).getString("status")) // n=56
    }
}
