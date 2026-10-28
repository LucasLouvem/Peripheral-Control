from hidctl.models import MouseProfile


def test_default_mouse_profile_has_five_dpi_stages():
    profile = MouseProfile()
    assert len(profile.dpi_stages) == 5
    assert profile.active_dpi in profile.dpi_stages
