from .version import __version__


def app_version(request):
    """Expose the app version to every template (shown in the footer)."""
    return {"app_version": __version__}
