def index(request):
    return render_page(request)


def render_page(request):
    return request


class PostView:
    @classmethod
    def as_view(cls):
        return cls
