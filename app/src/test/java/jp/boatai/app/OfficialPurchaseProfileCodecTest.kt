package jp.boatai.app

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Test

class OfficialPurchaseProfileCodecTest {
    private fun validJson(): String {
        val lanes = JSONObject()
        for (position in 1..3) {
            val boats = JSONObject()
            for (boat in 1..6) boats.put("$boat", JSONObject().put("id", "position-$position-$boat"))
            lanes.put("$position", boats)
        }
        return JSONObject()
            .put("venues", JSONObject().put("1", JSONObject().put("id", "venue-1")))
            .put("races", JSONObject().put("1", JSONObject().put("id", "race-1")))
            .put("trifecta", JSONObject().put("label", "3連単"))
            .put("lanes", lanes)
            .put("amount", JSONObject().put("id", "amount"))
            .put("add", JSONObject().put("id", "add"))
            .put("review", JSONObject().put("id", "review"))
            .toString()
    }

    @Test fun importsFullyMappedLocalSelectors() {
        val profile = OfficialPurchaseProfileCodec.decode(validJson())
        assertNotNull(profile)
        assertEquals("venue-1", profile!!.venueSelectors.getValue(1).resourceId)
        assertEquals("position-3-6", profile.laneSelectors.getValue(3).getValue(6).resourceId)
    }

    @Test fun rejectsMissingMappingsAndUnboundedJson() {
        assertNull(OfficialPurchaseProfileCodec.decode("{}"))
        assertNull(OfficialPurchaseProfileCodec.decode("x".repeat(24_001)))
        val json = JSONObject(validJson())
        json.getJSONObject("lanes").getJSONObject("1").remove("6")
        assertNull(OfficialPurchaseProfileCodec.decode(json.toString()))
    }
}
