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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.util.Locale

@Composable
fun PendingPurchaseCard(
    session: PendingPurchaseSession,
    vm: BoatViewModel,
    showLaunchFallback: Boolean = false
) {
    val selected = session.selectedRaces

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = androidx.compose.material3.MaterialTheme.colorScheme.tertiaryContainer)
    ) {
        Column(Modifier.padding(14.dp)) {
            Text("公式投票待ち", fontWeight = FontWeight.Bold, style = androidx.compose.material3.MaterialTheme.typography.titleMedium)
            Text(
                "候補全体 ${session.races.size}レース / ${session.ticketCount}点 / ${purchaseMoney(session.totalStake)}",
                style = androidx.compose.material3.MaterialTheme.typography.bodySmall
            )
            Spacer(Modifier.height(4.dp))
            Text(
                "選択中 ${selected.size}レース / ${session.selectedTicketCount}点 / ${purchaseMoney(session.selectedStake)}",
                fontWeight = FontWeight.Bold,
                style = androidx.compose.material3.MaterialTheme.typography.titleMedium
            )
            Text(
                "チェック中のレースだけ買い目をコピーします。公式側で内容・金額を確認して投票し、戻ってから実購入として確定してください。",
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
            Button(
                onClick = vm::openOfficialPurchase,
                enabled = selected.isNotEmpty(),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    if (selected.isEmpty()) {
                        "投票するレースを選択"
                    } else {
                        "${selected.size}レース・${purchaseMoney(session.selectedStake)}を公式投票へ"
                    }
                )
            }
            if (showLaunchFallback) {
                Spacer(Modifier.height(6.dp))
                OutlinedButton(
                    onClick = vm::openOfficialPurchaseFallback,
                    enabled = selected.isNotEmpty(),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("購入画面が開かない場合：別の公式投票サイト")
                }
            }
            Spacer(Modifier.height(6.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                OutlinedButton(
                    onClick = vm::selectAllPendingPurchaseRaces,
                    enabled = selected.size < session.races.size,
                    modifier = Modifier.weight(1f)
                ) {
                    Text("全選択")
                }
                OutlinedButton(
                    onClick = {
                        session.selectedRaceIds.toList().forEach(vm::togglePendingPurchaseRace)
                    },
                    enabled = selected.isNotEmpty(),
                    modifier = Modifier.weight(1f)
                ) {
                    Text("全解除")
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
