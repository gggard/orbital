import pytest
from conftest import make_app

from orbital_cli import manifest
from orbital_cli.errors import CliError, ExitCode

FULL = """
slug = "sales"
repo_url = "https://github.com/acme/sales"
branch = "prod"
main_file = "app.py"
public = false
allowed_groups = ["sales"]
tags = ["Team:Sales"]

[hibernate]
enabled = true
after_seconds = 3600

[poll]
enabled = true
interval_seconds = 300
"""


def test_parse_flattens_tables_and_defaults_type():
    spec = manifest.parse(FULL)
    assert spec == {
        "slug": "sales",
        "repo_url": "https://github.com/acme/sales",
        "branch": "prod",
        "main_file": "app.py",
        "public": False,
        "allowed_groups": ["sales"],
        "tags": ["Team:Sales"],
        "hibernate_enabled": True,
        "hibernate_after_seconds": 3600,
        "poll_enabled": True,
        "poll_interval_seconds": 300,
        "app_type": "streamlit",
    }


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('repo_url = "x"', "missing required key 'slug'"),
        ('slug = "a"', "missing required key 'repo_url'"),
        ('slug = "a"\nrepo_url = "x"\nfoo = 1', "unknown key 'foo'"),
        ('slug = "a"\nrepo_url = "x"\npublic = "yes"', "public must be a bool"),
        ('slug = "a"\nrepo_url = "x"\ntags = [1]', "tags must be a list of strings"),
        ('slug = "a"\nrepo_url = "x"\napp_type = "php"', "app_type must be one of"),
        ('slug = "a"\nrepo_url = "x"\nbuild_command = "npm run b"', "does not apply to streamlit"),
        ('slug = "a"\nrepo_url = "x"\napp_type = "static"\nmain_file = "a.py"', "does not apply"),
        ('slug = "a"\nrepo_url = "x"\n[hibernate]\nafter_seconds = true', "must be a int"),
        ('slug = "a"\nrepo_url = "x"\n[hibernate]\nafter_seconds = 0', "must be positive"),
        ('slug = "a"\nrepo_url = "x"\n[hibernate]\nidle = 1', "unknown key hibernate.idle"),
        ('slug = "a"\nrepo_url = "x"\nhibernate = 1', "[hibernate] must be a table"),
        ('slug = "a"\nrepo_url = "x"\nsecrets_toml = "k=1"', "secrets don't belong"),
        ('slug = "a"\nrepo_url = "x"\n[secrets]\nk = 1', "secrets don't belong"),
        ("slug = ", "invalid TOML"),
    ],
)
def test_parse_rejects(text, message):
    with pytest.raises(CliError) as e:
        manifest.parse(text)
    assert e.value.code == ExitCode.USAGE
    assert message in e.value.message


def test_load_missing_file(tmp_path):
    with pytest.raises(CliError) as e:
        manifest.load(tmp_path / "nope.toml")
    assert e.value.code == ExitCode.USAGE


def test_plan_create():
    plan = manifest.plan(manifest.parse(FULL), None, redeploy=False)
    assert plan.action == "create"
    assert plan.redeploy is True  # the first build always happens
    assert plan.changes["branch"] == {"from": None, "to": "prod"}
    assert "slug" not in plan.changes
    assert plan.describe().startswith("app sales: create")


def test_plan_update_only_changed_fields_and_normalizes_sets():
    spec = manifest.parse(FULL)
    app = make_app(
        slug="sales",
        repo_url="https://github.com/acme/sales",
        branch="prod",
        main_file="app.py",
        public=True,
        allowed_groups=["sales"],
        tags=["team:sales"],
        hibernate_enabled=True,
        hibernate_after_seconds=3600,
        poll_enabled=True,
        poll_interval_seconds=300,
    )
    plan = manifest.plan(spec, app, redeploy=True)
    assert plan.action == "update"
    assert plan.changes == {"public": {"from": True, "to": False}}
    assert plan.redeploy and not plan.rebuild_by_patch
    assert plan.reason == "redeploy (branch prod)"
    assert "public  true -> false" in plan.describe()


def test_plan_rebuild_fields_rely_on_patch():
    spec = manifest.parse('slug = "demo"\nrepo_url = "https://github.com/x/y"\nbranch = "dev"')
    plan = manifest.plan(spec, make_app(), redeploy=False)
    assert plan.rebuild_by_patch and plan.redeploy
    assert plan.reason.startswith("rebuild")


def test_plan_noop_and_no_redeploy():
    spec = manifest.parse('slug = "demo"\nrepo_url = "https://github.com/x/y"')
    plan = manifest.plan(spec, make_app(), redeploy=False)
    assert plan.action == "none" and not plan.redeploy
    assert "settings up to date" in plan.describe()
    assert "--no-redeploy" in plan.describe()


def test_plan_skips_redeploy_while_building():
    spec = manifest.parse('slug = "demo"\nrepo_url = "https://github.com/x/y"')
    plan = manifest.plan(spec, make_app(state="building"), redeploy=True)
    assert not plan.redeploy
    assert "already in progress" in plan.reason


def test_plan_rejects_immutable_change():
    spec = manifest.parse('slug = "demo"\nrepo_url = "https://github.com/other/repo"')
    with pytest.raises(CliError) as e:
        manifest.plan(spec, make_app(), redeploy=True)
    assert e.value.code == ExitCode.USAGE
    assert "can't change after creation" in e.value.message


def test_plan_to_dict():
    spec = manifest.parse('slug = "demo"\nrepo_url = "https://github.com/x/y"\npublic = false')
    d = manifest.plan(spec, make_app(), redeploy=True).to_dict()
    assert d == {
        "action": "update",
        "slug": "demo",
        "changes": {"public": {"from": True, "to": False}},
        "redeploy": True,
        "reason": "redeploy (branch main)",
    }
