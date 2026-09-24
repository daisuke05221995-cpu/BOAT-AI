package jp.boatai.app

import org.json.JSONObject

object BoatRaceJsonParser {
    fun parse(json: String): List<RaceData> {
        val root = JSONObject(json)
        val stadiums = root.optJSONObject("programs")?.optJSONObject("stadiums") ?: return emptyList()
        val result = mutableListOf<RaceData>()

        val stadiumKeys = stadiums.keys().asSequence().mapNotNull { it.toIntOrNull() }.sorted()
        for (stadiumNumber in stadiumKeys) {
            val stadium = stadiums.optJSONObject(stadiumNumber.toString()) ?: continue
            val races = stadium.optJSONObject("races") ?: continue
            val raceKeys = races.keys().asSequence().mapNotNull { it.toIntOrNull() }.sorted()
            for (raceNumber in raceKeys) {
                val raceObj = races.optJSONObject(raceNumber.toString()) ?: continue
                result += parseRace(raceObj, stadiumNumber, raceNumber)
            }
        }
        return result.sortedWith(compareBy<RaceData> { it.stadiumNumber }.thenBy { it.raceNumber })
    }

    private fun parseRace(obj: JSONObject, stadiumNumber: Int, raceNumber: Int): RaceData {
        val previewObj = obj.optJSONObject("preview")
        val previewRacers = parsePreviewRacers(previewObj?.optJSONObject("racers"))

        val racers = buildList {
            val racersObj = obj.optJSONObject("racers")
            if (racersObj != null) {
                for (lane in 1..6) {
                    val r = racersObj.optJSONObject(lane.toString()) ?: continue
                    val rankText = r.optTextOrNull("rank_number_source")
                        ?: r.optIntOrNull("rank_number")?.toString()
                        ?: "-"
                    add(
                        Racer(
                            lane = lane,
                            name = r.optString("name").trim(),
                            registrationNumber = r.optIntOrNull("number"),
                            rank = rankText,
                            branch = r.optTextOrNull("branch_number_source") ?: r.optIntOrNull("branch_number")?.toString(),
                            age = r.optIntOrNull("age"),
                            weight = r.optDoubleOrNull("weight"),
                            averageStart = r.optDoubleOrNull("average_start_timing"),
                            nationalWinRate = r.optDoubleOrNull("national_win_rate"),
                            nationalTop2 = r.optDoubleOrNull("national_top_2_percent"),
                            nationalTop3 = r.optDoubleOrNull("national_top_3_percent"),
                            localWinRate = r.optDoubleOrNull("local_win_rate"),
                            localTop2 = r.optDoubleOrNull("local_top_2_percent"),
                            localTop3 = r.optDoubleOrNull("local_top_3_percent"),
                            motorNumber = r.optIntOrNull("motor_number"),
                            motorTop2 = r.optDoubleOrNull("motor_top_2_percent"),
                            motorTop3 = r.optDoubleOrNull("motor_top_3_percent"),
                            boatNumber = r.optIntOrNull("boat_number"),
                            boatTop2 = r.optDoubleOrNull("boat_top_2_percent"),
                            boatTop3 = r.optDoubleOrNull("boat_top_3_percent"),
                            preview = previewRacers[lane],
                            classNumber = r.optIntOrNull("rank_number")
                                ?: r.optIntOrNull("racer_class_number")
                                ?: classNumberFromText(rankText),
                            flyingCount = r.optIntOrNull("flying_count") ?: r.optIntOrNull("racer_flying_count"),
                            lateCount = r.optIntOrNull("late_count") ?: r.optIntOrNull("racer_late_count")
                        )
                    )
                }
            }
        }

        val preview = previewObj?.let {
            PreviewData(
                windSpeed = it.optIntOrNull("wind_speed"),
                windDirection = it.optTextOrNull("wind_direction_number_source")
                    ?: it.optIntOrNull("wind_direction_number")?.toString(),
                waveHeight = it.optIntOrNull("wave_height"),
                weather = it.optTextOrNull("weather_number_source")
                    ?: it.optIntOrNull("weather_number")?.toString(),
                airTemperature = it.optDoubleOrNull("air_temperature"),
                waterTemperature = it.optDoubleOrNull("water_temperature")
            )
        }

        val resultObj = obj.optJSONObject("result")
        val trifectaArray = resultObj?.optJSONObject("payouts")?.optJSONArray("trifecta")
        val trifecta = trifectaArray?.optJSONObject(0)
        val raceResult = if (resultObj != null) {
            RaceResultData(
                trifectaCombination = trifecta?.optTextOrNull("combination"),
                trifectaPayout = trifecta?.optIntOrNull("amount"),
                technique = resultObj.optTextOrNull("technique_number_source")
                    ?: resultObj.optIntOrNull("technique_number")?.toString()
            )
        } else null

        return RaceData(
            date = obj.optString("date"),
            stadiumNumber = obj.optIntOrNull("stadium_number") ?: stadiumNumber,
            raceNumber = obj.optIntOrNull("race_number") ?: raceNumber,
            closedAt = obj.optString("closed_at"),
            gradeNumber = obj.optIntOrNull("grade_number"),
            title = obj.optString("title"),
            subtitle = obj.optString("subtitle"),
            distance = obj.optIntOrNull("distance"),
            dayNumber = obj.optIntOrNull("day_number"),
            racers = racers,
            preview = preview,
            result = raceResult
        )
    }

    private fun parsePreviewRacers(obj: JSONObject?): Map<Int, PreviewRacer> {
        if (obj == null) return emptyMap()
        return buildMap {
            for (lane in 1..6) {
                val r = obj.optJSONObject(lane.toString()) ?: continue
                put(
                    lane,
                    PreviewRacer(
                        course = r.optIntOrNull("course_number"),
                        startTiming = r.optDoubleOrNull("start_timing"),
                        weight = r.optDoubleOrNull("weight"),
                        weightAdjustment = r.optDoubleOrNull("weight_adjustment"),
                        exhibitionTime = r.optDoubleOrNull("exhibition_time"),
                        tilt = r.optDoubleOrNull("tilt_adjustment")
                    )
                )
            }
        }
    }

    private fun classNumberFromText(value: String): Int? = when (value.trim().uppercase()) {
        "A1" -> 1
        "A2" -> 2
        "B1" -> 3
        "B2" -> 4
        else -> null
    }
}
