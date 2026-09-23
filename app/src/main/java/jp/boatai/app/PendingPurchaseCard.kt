package jp.boatai.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.util.Locale

@Composable
fun PendingPurchaseCard(session: PendingPurchaseSession, vm: BoatViewModel) {
    val uriHandler = LocalUriHandler.current
    val selected = session.selectedRaces

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = androidx.compose.material3.MaterialTheme.colorScheme.tertiaryContainer)
    ) {
        Column(Modifier.padding(14.dp)) {
            Text("公式投票待ち", fontWeight = FontWeight.Bold, style = androidx.compose.material3.MaterialTheme.typography.titleMedium)
            Text(
                "${session.races.size}レース / ${session.ticketCount}点 / 合計 ${purchaseMoney(session.totalStake)}",
                fontWeight = FontWeight.Bold
            )
            Text(
                "公式サイトで実際に投票できたレースだけチェックを残し、戻ってから実購入として確定してください。",
                style = androidx.compose.material3.MaterialTheme.typography.bodySmall
            )
            Spacer(Modifier.height(8.dp))

            session.races.forEachIndexed { index, race ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.Top
                ) {
                    Checkbox(
                        checked = race.raceId in session.selectedRaceIds,
                        onCheckedChange = { vm.togglePendingPurchaseRace(race.raceId) }
                    )
                    Column(Modifier.weight(1f)) {
                        Text("${race.venueName} ${race.raceNumber}R　${purchaseMoney(race.totalStake)}", fontWeight = FontWeight.SemiBold)
                        Text(
                            race.tickets.joinToString(" / ") { "${it.combination} ${purchaseMoney(it.amount)}" },
                            style = androidx.compose.material3.MaterialTheme.typography.bodySmall
                        )
                    }
                }
                if (index < session.races.lastIndex) HorizontalDivider(Modifier.padding(vertical = 4.dp))
            }

            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Button(onClick = { uriHandler.openUri(PendingPurchaseStore.OFFICIAL_SIMPLE_BET_URL) }) {
                    Text("公式投票サイト")
                }
                OutlinedButton(onClick = vm::selectAllPendingPurchaseRaces) {
                    Text("全選択")
                }
            }
            Spacer(Modifier.height(8.dp))
            ConfirmPurchaseButton(
                label = "${selected.size}レースを投票完了として記録",
                summary = "公式サイトで実際に投票した${selected.size}レース・${session.selectedTicketCount}点・合計${purchaseMoney(session.selectedStake)}を実購入として損益に記録します。投票していないレースはチェックを外してください。",
                enabled = selected.isNotEmpty(),
                modifier = Modifier.fillMaxWidth(),
                onConfirm = vm::confirmPendingPurchase
            )
            TextButton(onClick = vm::cancelPendingPurchase, modifier = Modifier.fillMaxWidth()) {
                Text("今回は購入しなかった / 投票待ちを破棄")
            }
        }
    }
}

private fun purchaseMoney(value: Int): String = String.format(Locale.JAPAN, "%,d円", value)
