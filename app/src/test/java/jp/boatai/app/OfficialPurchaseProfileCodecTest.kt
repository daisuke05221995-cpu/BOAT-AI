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

    @Test fun readsOptionalFinalizationOnlyWhenAllFieldsPresent() {
        val json = JSONObject(validJson()).put("finalization", JSONObject()
            .put("next", JSONObject().put("id", "official:next"))
            .put("confirmAmount", JSONObject().put("id", "official:confirm_amount"))
            .put("rowId", "official:ticket_row")
            .put("totalId", "official:total")
            .put("rowPattern", "(.+?) (\\d{1,2})R ([1-6]-[1-6]-[1-6]) ([0-9]+)円")
            .put("totalPattern", "合計 ([0-9]+)円")
            .put("title", JSONObject().put("id", "official:review_title"))
            .put("submit", JSONObject().put("id", "official:submit")))
        assertNotNull(OfficialPurchaseProfileCodec.decode(json.toString())?.finalization)
        json.getJSONObject("finalization").remove("submit")
        assertNull(OfficialPurchaseProfileCodec.decode(json.toString()))
    }
}
