import os
import stat
import tomllib

import pytest

from orbital_cli import config
from orbital_cli.errors import CliError, ExitCode


def test_defaults_without_anything(isolated_env):
    s = config.resolve(env={"ORBITAL_CONFIG": str(isolated_env)})
    assert s.url == config.DEFAULT_URL
    assert s.token is None
    assert s.profile == "default"
    assert s.output is None


def test_precedence_flag_over_env_over_file(isolated_env):
    config.save_profile(isolated_env, "prod", url="https://file.example", token="orbpat_file")
    env = {"ORBITAL_CONFIG": str(isolated_env)}
    assert config.resolve(env=env).url == "https://file.example"
    assert config.resolve(env=env).token == "orbpat_file"

    env |= {"ORBITAL_URL": "https://env.example/", "ORBITAL_TOKEN": "orbpat_env"}
    s = config.resolve(env=env)
    assert (s.url, s.token) == ("https://env.example", "orbpat_env")  # trailing / stripped

    s = config.resolve(url="https://flag.example", token="orbpat_flag", env=env)
    assert (s.url, s.token) == ("https://flag.example", "orbpat_flag")


def test_profiles_and_default_profile(isolated_env):
    config.save_profile(isolated_env, "prod", url="https://prod", token="p")
    config.save_profile(isolated_env, "staging", url="https://staging", token="s")
    env = {"ORBITAL_CONFIG": str(isolated_env)}
    assert config.resolve(env=env).profile == "prod"  # first saved becomes the default
    assert config.resolve(profile="staging", env=env).url == "https://staging"
    assert config.resolve(env=env | {"ORBITAL_PROFILE": "staging"}).token == "s"


def test_unknown_explicit_profile_is_an_error(isolated_env):
    env = {"ORBITAL_CONFIG": str(isolated_env)}
    with pytest.raises(CliError) as e:
        config.resolve(profile="nope", env=env)
    assert e.value.code == ExitCode.USAGE
    # ... except for commands that create it (login)
    assert config.resolve(profile="nope", env=env, strict_profile=False).profile == "nope"


def test_output_validation(isolated_env):
    env = {"ORBITAL_CONFIG": str(isolated_env)}
    assert config.resolve(env=env | {"ORBITAL_OUTPUT": "json"}).output == "json"
    with pytest.raises(CliError) as e:
        config.resolve(output="yaml", env=env)
    assert e.value.code == ExitCode.USAGE


def test_saved_file_is_private_and_round_trips(isolated_env):
    config.save_profile(isolated_env, "prod", url="https://x", token='tok"with\\quotes')
    assert stat.S_IMODE(os.stat(isolated_env).st_mode) == 0o600
    data = tomllib.loads(isolated_env.read_text())
    assert data == {
        "default_profile": "prod",
        "profiles": {"prod": {"url": "https://x", "token": 'tok"with\\quotes'}},
    }


def test_save_preserves_other_settings(isolated_env):
    isolated_env.parent.mkdir(parents=True)
    isolated_env.write_text(
        'default_profile = "a"\n[profiles.a]\nurl = "https://a"\noutput = "json"\n'
    )
    os.chmod(isolated_env, 0o600)
    config.save_profile(isolated_env, "a", url="https://a2", token="t")
    data = tomllib.loads(isolated_env.read_text())
    assert data["profiles"]["a"] == {"url": "https://a2", "output": "json", "token": "t"}


def test_remove_token(isolated_env):
    config.save_profile(isolated_env, "prod", url="https://x", token="t")
    assert config.remove_token(isolated_env, "prod") is True
    assert config.remove_token(isolated_env, "prod") is False
    assert "token" not in tomllib.loads(isolated_env.read_text())["profiles"]["prod"]


def test_world_readable_file_warns(isolated_env, capsys):
    config.save_profile(isolated_env, "prod", url="https://x", token="t")
    os.chmod(isolated_env, 0o644)
    config.load_file(isolated_env)
    assert "chmod 600" in capsys.readouterr().err


def test_invalid_config_file(isolated_env):
    isolated_env.parent.mkdir(parents=True)
    isolated_env.write_text("not = [valid")
    os.chmod(isolated_env, 0o600)
    with pytest.raises(CliError) as e:
        config.load_file(isolated_env)
    assert e.value.code == ExitCode.USAGE
