from fermentation_agent.models import Mixing
from fermentation_agent.tools.water_temp import calculate_water_temperature


def test_hand_mixing():
    result = calculate_water_temperature(23, room_temp_c=22, mixing=Mixing.HAND)
    assert result.water_temp_c == 23
    assert result.warnings == []


def test_stand_mixer_needs_colder_water():
    assert calculate_water_temperature(23, room_temp_c=22, mixing=Mixing.STAND_MIXER).water_temp_c == 17


def test_explicit_flour_temperature():
    assert calculate_water_temperature(23, 22, Mixing.HAND, flour_temp_c=18).water_temp_c == 27


def test_warns_when_ice_water_needed():
    result = calculate_water_temperature(23, room_temp_c=34, mixing=Mixing.STAND_MIXER)
    assert result.water_temp_c < 2
    assert "ice water" in result.warnings[0]


def test_warns_when_water_too_hot():
    result = calculate_water_temperature(26, room_temp_c=12, mixing=Mixing.HAND)
    assert result.water_temp_c > 35
    assert result.warnings
