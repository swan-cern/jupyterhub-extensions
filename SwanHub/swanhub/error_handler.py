
import jupyterhub.handlers.pages as pages


class ProxyErrorHandler(pages.ProxyErrorHandler):
    """
        Handler for rendering proxy error pages.
        We need to overwrite the default to redirect users to the proper place. The default
        error message adds a link to the home, but since we removed the "Shutdown my container"
        button, users are unable to clear their states.
    """

    def get(self, status_code_s):
        status_code = int(status_code_s)

        # If the error is container not reachable, redirect to home#changeconfig
        # where the cleanup will take place (including removing the stored configuration 
        # which might be causing the problem)
        if status_code == 503:
            html = self.render_template(
                'unreachable_container.html',
            )
            self.finish(html)

        else:
            super().get(status_code_s)