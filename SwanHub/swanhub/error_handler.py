from jupyterhub.handlers import pages
from jupyterhub.utils import url_path_join


class ProxyErrorHandler(pages.ProxyErrorHandler):
    """
    Handler for rendering proxy error pages.
    We need to overwrite the default to link users to the proper place. The default
    error message adds a link to the home, but since we removed the "Shutdown my container"
    button, users are unable to clear their states.
    """

    async def get(self, status_code_s):
        status_code = int(status_code_s)

        # If the error is container not reachable, link to home#changeconfig
        # where the cleanup will take place (including removing the stored configuration
        # which might be causing the problem)
        if status_code == 503:
            link_url = url_path_join(self.hub.base_url, "home?changeconfig")
            html = await self.render_template(
                "error.html",
                status_code=503,
                status_message="Session unreachable",
                message_html=f'Your session appears to be down. Try <a href="{link_url}">restarting it</a>.',
            )
            self.finish(html)

        else:
            await super().get(status_code_s)
