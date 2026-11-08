package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CollectorHandoffNoticePolicyTest {
    private val now = 1_800_000_000_000L
    private val expires = now + 60_000L

    @Test fun newValidHandoffNotifies() {
        assertTrue(CollectorHandoffNoticePolicy.shouldNotify(true, "handoff-1", expires, now, null))
    }

    @Test fun sameHandoffNeverNotifiesTwice() {
        assertFalse(CollectorHandoffNoticePolicy.shouldNotify(true, "handoff-1", expires, now, "handoff-1"))
        assertTrue(CollectorHandoffNoticePolicy.shouldNotify(true, "handoff-2", expires, now, "handoff-1"))
    }

    @Test fun disabledNotificationsNeverPost() {
        assertFalse(CollectorHandoffNoticePolicy.shouldNotify(false, "handoff-2", expires, now, null))
    }

    @Test fun expiredHandoffIsNotAnnounced() {
        assertFalse(CollectorHandoffNoticePolicy.shouldNotify(true, "handoff-1", now, now, null))
        assertFalse(CollectorHandoffNoticePolicy.shouldNotify(true, "handoff-1", now - 1L, now, null))
    }

    @Test fun blankHandoffIdIsRejected() {
        assertFalse(CollectorHandoffNoticePolicy.shouldNotify(true, "", expires, now, null))
    }

    @Test fun summaryShowsReceivedRaceTicketAndTotalWithoutSensitiveIdentifiers() {
        assertEquals(
            "2レース・5点・合計2,500円。BOAT AIで内容を確認してください",
            CollectorHandoffNoticePolicy.summary(2, 5, 2500)
        )
    }

    @Test fun eachDistinctTransferUsesItsOwnAndroidNotificationId() {
        val first = CollectorHandoffNoticePolicy.notificationId("11111111-1111-1111-1111-111111111111")
        val repeat = CollectorHandoffNoticePolicy.notificationId("11111111-1111-1111-1111-111111111111")
        val second = CollectorHandoffNoticePolicy.notificationId("22222222-2222-2222-2222-222222222222")
        assertEquals(first, repeat)
        assertTrue(first > 0)
        assertTrue(second > 0)
        assertFalse(first == second)
    }

    @Test fun aNotificationDoesNotMeanWagerWasSubmitted() {
        val message = CollectorHandoffNoticePolicy.summary(1, 1, 500)
        assertFalse(message.contains("購入完了"))
        assertFalse(message.contains("投票成立"))
    }
}
