# syntax=docker/dockerfile:1
# En el servidor, pasar la imagen/digest que utiliza actualmente cada instancia.
ARG ODOO_BASE_IMAGE=odoo@sha256:f99ffac95cb39a0924622ea4118481c95651d9c84187e5b30a21c2cc4419c7dd
FROM ${ODOO_BASE_IMAGE}

USER root
COPY requirements.txt requirements-odoo.txt /tmp/licitaciones-dependencies/
RUN python3 -m pip install --no-cache-dir --break-system-packages \
        -r /tmp/licitaciones-dependencies/requirements.txt \
    && python3 -m pip install --no-cache-dir --no-deps --require-hashes \
        --only-binary=:all: --target /tmp/licitaciones-oca \
        -r /tmp/licitaciones-dependencies/requirements-odoo.txt

# /mnt/extra-addons se monta desde el host. El addon OCA se incorpora a los addons
# nativos de esta imagen para que ese montaje no oculte la dependencia.
RUN python3 - <<'PY'
import ast
import shutil
from pathlib import Path

import odoo
from odoo import release
import openpyxl
import xlsxwriter
import xlrd

if release.version_info[:2] != (19, 0):
    raise RuntimeError('La imagen base debe contener Odoo 19.0.')
source = Path('/tmp/licitaciones-oca/odoo/addons/report_xlsx')
manifest = ast.literal_eval((source / '__manifest__.py').read_text())
if not manifest['version'].startswith('19.0.'):
    raise RuntimeError('report_xlsx debe corresponder a Odoo 19.0.')
target = Path(odoo.__file__).resolve().parent / 'addons' / 'report_xlsx'
if target.exists():
    raise RuntimeError('La imagen base ya contiene report_xlsx; revisar antes de reemplazarlo.')
shutil.copytree(source, target)
shutil.rmtree('/tmp/licitaciones-oca')
shutil.rmtree('/tmp/licitaciones-dependencies')
print('Dependencias disponibles: openpyxl, xlsxwriter, xlrd y report_xlsx', manifest['version'])
PY

USER odoo
