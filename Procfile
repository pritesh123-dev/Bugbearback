web: gunicorn bugback.wsgi --log-file - 
#or works good with external database
web: python manage.py migrate && gunicorn bugback.wsgi