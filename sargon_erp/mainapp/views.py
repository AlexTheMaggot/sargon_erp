from django.shortcuts import render


def index(request):
    template = 'mainapp/index.html'
    return render(request, template)