package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class BoatRaceJsonParserModelAFieldsTest {
    @Test
    fun retainsNormalizedFieldsNeededByModelA() {
        val json = """
            {
              "programs": {
                "stadiums": {
                  "12": {
                    "races": {
                      "7": {
                        "date": "2026-09-24",
                        "stadium_number": 12,
                        "race_number": 7,
                        "closed_at": "2026-09-24 17:00:00",
                        "racers": {
                          "1": {
                            "name": "Test Racer",
                            "number": 4321,
                            "rank_number": 1,
                            "rank_number_source": "A1",
                            "age": 33,
                            "weight": 52.0,
                            "flying_count": 2,
                            "late_count": 1,
                            "average_start_timing": 0.15,
                            "national_win_rate": 7.2,
                            "national_top_2_percent": 45.0,
                            "national_top_3_percent": 65.0,
                            "local_win_rate": 6.8,
                            "local_top_2_percent": 41.0,
                            "local_top_3_percent": 61.0,
                            "motor_number": 11,
                            "motor_top_2_percent": 32.0,
                            "motor_top_3_percent": 51.0,
                            "boat_number": 22,
                            "boat_top_2_percent": 30.0,
                            "boat_top_3_percent": 49.0
                          }
                        },
                        "preview": {
                          "wind_speed": 3,
                          "wind_direction_number": 7,
                          "wind_direction_number_source": "南東",
                          "wave_height": 4,
                          "weather_number": 1,
                          "weather_number_source": "晴",
                          "air_temperature": 25.5,
                          "water_temperature": 24.0,
                          "racers": {
                            "1": {
                              "course_number": 1,
                              "start_timing": 0.12,
                              "weight": 52.0,
                              "weight_adjustment": 0.0,
                              "exhibition_time": 6.72,
                              "tilt_adjustment": 0.0
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
        """.trimIndent()

        val race = BoatRaceJsonParser.parse(json).single()
        val racer = race.racers.single()
        assertEquals(4321, racer.registrationNumber)
        assertEquals(1, racer.classNumber)
        assertEquals(2, racer.flyingCount)
        assertEquals(1, racer.lateCount)
        assertEquals("A1", racer.rank)
        assertNotNull(racer.preview)
        assertEquals(7, race.preview?.windDirectionNumber)
        assertEquals("南東", race.preview?.windDirection)
    }
}
