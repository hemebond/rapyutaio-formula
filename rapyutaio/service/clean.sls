# -*- coding: utf-8 -*-
# vim: ft=sls

{#- Get the `tplroot` from `tpldir` #}
{%- set tplroot = tpldir.split('/')[0] %}
{%- from tplroot ~ "/map.jinja" import rapyutaio with context %}

rapyutaio-service-clean-service-dead:
  service.dead:
    - name: {{ rapyutaio.service.name }}
    - enable: False
