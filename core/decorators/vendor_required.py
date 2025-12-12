from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

def vendor_required(view_func):
    @login_required(login_url='login')
    def wrapper(request, *args, **kwargs):
        if request.user.role != "vendor":
            return redirect("home")
        return view_func(request, *args, **kwargs)
    return wrapper
