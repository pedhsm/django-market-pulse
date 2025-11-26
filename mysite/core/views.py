from django.shortcuts import render

# Create your views here.
def index(request):
    context = {'greeting':  'Nao posso esquecer de tirar isso do Django!'}
    return render(request, 'index.html',context)