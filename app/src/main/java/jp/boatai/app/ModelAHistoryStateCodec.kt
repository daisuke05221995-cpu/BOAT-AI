package jp.boatai.app

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.nio.charset.StandardCharsets

/**
 * Compact, lossless binary codec for ModelAPlayerHistory.State.
 *
 * Statistics remain IEEE-754 doubles. Recent player history stores day deltas as
 * unsigned varints and reconstructs cumulative top1/top2/top3 counts from one
 * 3-bit outcome byte per appearance. This avoids shipping the ~46.9 MB research
 * JSON representation while preserving the exact information needed at inference.
 */
internal object ModelAHistoryStateCodec {
    private val MAGIC = byteArrayOf('B'.code.toByte(), 'A'.code.toByte(), 'H'.code.toByte(), '1'.code.toByte())
    private const val VERSION = 1

    data class Metadata(
        val bytes: Int,
        val stats: Int,
        val players: Int,
        val appearances: Int,
        val lastDay: Int,
        val updateRaces: Int
    )

    fun encode(state: ModelAPlayerHistory.State): ByteArray {
        val output = ByteArrayOutputStream()
        DataOutputStream(output).use { data ->
            data.write(MAGIC)
            data.writeInt(VERSION)
            data.writeInt(state.lastDay)
            data.writeInt(state.updateRaces)

            val stats = state.stats.toSortedMap()
            data.writeInt(stats.size)
            for ((key, values) in stats) {
                require(values.size == 8) { "History stats must contain eight values" }
                writeString(data, key)
                values.forEach(data::writeDouble)
            }

            val recent = state.recent.toSortedMap()
            data.writeInt(recent.size)
            for ((player, playerRecent) in recent) {
                require(playerRecent.cumulative.size == playerRecent.days.size + 1) {
                    "Recent cumulative length mismatch for player $player"
                }
                writeString(data, player)
                writeUnsignedVarInt(data, playerRecent.days.size)
                var previousDay = 0
                var previousCounts = intArrayOf(0, 0, 0)
                for (index in playerRecent.days.indices) {
                    val day = playerRecent.days[index]
                    require(day >= previousDay) { "Recent days must be sorted" }
                    writeUnsignedVarInt(data, day - previousDay)
                    previousDay = day

                    val currentCounts = playerRecent.cumulative[index + 1]
                    require(currentCounts.size == 3)
                    val delta = IntArray(3) { metric -> currentCounts[metric] - previousCounts[metric] }
                    require(delta.all { it == 0 || it == 1 }) { "Recent outcome delta must be binary" }
                    require(delta[0] <= delta[1] && delta[1] <= delta[2]) { "Invalid cumulative finish flags" }
                    val packed = delta[0] or (delta[1] shl 1) or (delta[2] shl 2)
                    data.writeByte(packed)
                    previousCounts = currentCounts.copyOf()
                }
            }
        }
        return output.toByteArray()
    }

    fun decode(bytes: ByteArray): ModelAPlayerHistory.State {
        DataInputStream(ByteArrayInputStream(bytes)).use { data ->
            val magic = ByteArray(MAGIC.size)
            data.readFully(magic)
            require(magic.contentEquals(MAGIC)) { "Invalid Model A history state magic" }
            require(data.readInt() == VERSION) { "Unsupported Model A history state version" }
            val lastDay = data.readInt()
            val updateRaces = data.readInt()
            require(lastDay >= 0 && updateRaces >= 0)

            val statCount = data.readInt()
            require(statCount >= 0)
            val stats = LinkedHashMap<String, DoubleArray>(statCount)
            repeat(statCount) {
                val key = readString(data)
                require(key !in stats) { "Duplicate history stat key $key" }
                stats[key] = DoubleArray(8) { data.readDouble() }
            }

            val playerCount = data.readInt()
            require(playerCount >= 0)
            val recent = LinkedHashMap<String, ModelAPlayerHistory.Recent>(playerCount)
            repeat(playerCount) {
                val player = readString(data)
                require(player !in recent) { "Duplicate history player $player" }
                val count = readUnsignedVarInt(data)
                val days = ArrayList<Int>(count)
                val cumulative = ArrayList<IntArray>(count + 1)
                cumulative += intArrayOf(0, 0, 0)
                var day = 0
                var counts = intArrayOf(0, 0, 0)
                repeat(count) {
                    day += readUnsignedVarInt(data)
                    days += day
                    val packed = data.readUnsignedByte()
                    require((packed and 0b11111000) == 0) { "Invalid packed history outcome" }
                    val delta = intArrayOf(packed and 1, (packed shr 1) and 1, (packed shr 2) and 1)
                    require(delta[0] <= delta[1] && delta[1] <= delta[2]) { "Invalid packed finish flags" }
                    counts = IntArray(3) { metric -> counts[metric] + delta[metric] }
                    cumulative += counts.copyOf()
                }
                recent[player] = ModelAPlayerHistory.Recent(days.toMutableList(), cumulative.toMutableList())
            }
            require(data.available() == 0) { "Trailing bytes in Model A history state" }
            return ModelAPlayerHistory.State(
                stats = stats.toMutableMap(),
                recent = recent.toMutableMap(),
                lastDay = lastDay,
                updateRaces = updateRaces
            )
        }
    }

    fun metadata(bytes: ByteArray, state: ModelAPlayerHistory.State): Metadata = Metadata(
        bytes = bytes.size,
        stats = state.stats.size,
        players = state.recent.size,
        appearances = state.recent.values.sumOf { it.days.size },
        lastDay = state.lastDay,
        updateRaces = state.updateRaces
    )

    private fun writeString(data: DataOutputStream, value: String) {
        val bytes = value.toByteArray(StandardCharsets.UTF_8)
        writeUnsignedVarInt(data, bytes.size)
        data.write(bytes)
    }

    private fun readString(data: DataInputStream): String {
        val length = readUnsignedVarInt(data)
        require(length <= 1_000_000) { "Unreasonable history string length" }
        val bytes = ByteArray(length)
        data.readFully(bytes)
        return String(bytes, StandardCharsets.UTF_8)
    }

    private fun writeUnsignedVarInt(data: DataOutputStream, input: Int) {
        require(input >= 0)
        var value = input
        while ((value and -128) != 0) {
            data.writeByte((value and 0x7f) or 0x80)
            value = value ushr 7
        }
        data.writeByte(value)
    }

    private fun readUnsignedVarInt(data: DataInputStream): Int {
        var result = 0
        var shift = 0
        while (shift < 35) {
            val byte = data.readUnsignedByte()
            result = result or ((byte and 0x7f) shl shift)
            if ((byte and 0x80) == 0) {
                require(result >= 0) { "Unsigned varint overflow" }
                return result
            }
            shift += 7
        }
        error("Malformed unsigned varint")
    }
}
