"""MkDocs build hook: attach per-page meta descriptions without editing the
source markdown, since several docs are read both on GitHub (as plain files)
and built into this site, and YAML front matter renders as ugly literal text
in GitHub's plain markdown view.
"""

DESCRIPTIONS = {
    "INSTALL.md": "Install the Orbital Helm chart on a real Kubernetes cluster.",
    "USER.md": "Deploy and manage your own Streamlit apps and static sites as an Orbital user.",
    "ADMIN.md": "Operate an Orbital platform — roles, RBAC, and upgrades.",
    "API.md": "Deploy and monitor Orbital apps via the REST API.",
    "UI-SPEC.md": "UI specification for the Orbital management console.",
    "DEVELOPMENT.md": "Set up a local Orbital development environment on minikube.",
    "CONTRIBUTING.md": "How to contribute to Orbital — PR and issue workflow.",
    "SPEC.md": "Full functional specification and architecture for Orbital.",
}


def on_page_markdown(markdown, page, config, files):
    page.meta.setdefault("description", DESCRIPTIONS.get(page.file.src_uri, config.site_description))
    return markdown
