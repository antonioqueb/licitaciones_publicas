#!/usr/bin/env bash
# Construye las dependencias sobre la imagen actual de cada instancia, sin reiniciarla.
set -euo pipefail

case "${1:-both}" in
    qa) instances=(qa) ;;
    production) instances=(production) ;;
    both) instances=(qa production) ;;
    *) printf 'Uso: bash %s [qa|production|both]\n' "$0" >&2; exit 2 ;;
esac

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
for instance in "${instances[@]}"; do
    instance_dir="/opt/bioteczac/$instance"
    compose_file="$instance_dir/compose.json"
    if [[ ! -f "$compose_file" ]]; then
        printf 'No existe la configuración de %s: %s\n' "$instance" "$compose_file" >&2
        exit 1
    fi
    if [[ -n "${ODOO_BASE_IMAGE:-}" ]]; then
        base_image="$ODOO_BASE_IMAGE"
    else
        base_image=$(python3 - "$compose_file" <<'PY'
import json
import sys

service = json.load(open(sys.argv[1]))['services']['odoo']
build = service.get('build') or {}
args = (build.get('args') or {}) if isinstance(build, dict) else {}
image = args.get('ODOO_BASE_IMAGE') if isinstance(args, dict) else None
image = image or service.get('image')
if not image or image.startswith('bioteczac-odoo-'):
    raise SystemExit('Especifique ODOO_BASE_IMAGE con la imagen original de Odoo 19.')
print(image)
PY
)
    fi
    image_tag="bioteczac-odoo-$instance-licitaciones:19.0.1.0.0"
    printf 'Construyendo %s desde %s\n' "$image_tag" "$base_image"
    ODOO_BASE_IMAGE="$base_image" LICITACIONES_IMAGE="$image_tag" LICITACIONES_BUILD_CONTEXT="$repo_dir" \
        docker compose --project-directory "$instance_dir" -p "bioteczac-$instance" \
        -f "$compose_file" -f "$repo_dir/compose.dependencies.yaml" build odoo
    printf 'Imagen construida para %s: %s\n' "$instance" "$image_tag"
done
