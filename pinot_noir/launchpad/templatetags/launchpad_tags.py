from django import template

from pinot_noir.launchpad.gravatar import gravatar_url

register = template.Library()
register.filter("gravatar_url", gravatar_url)
