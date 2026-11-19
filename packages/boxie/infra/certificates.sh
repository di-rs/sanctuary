#!/usr/bin/env bash
# All signing material stays in ca/. Runtime mounts expose only leaf identities.
set -euo pipefail
umask 077
[[ $# == 1 || $# == 3 ]] || exit 2
root=$1
[[ ! -L $root ]] || exit 1
# Each identity lists its path, issuer, DNS name, usage, and default UID/GID.
certificates='server/frontend frontend temporal serverAuth 1000
server/internode internode temporal-internode serverAuth,clientAuth 1000
api/boxie-api client boxie-api clientAuth 0
supervisor/boxie-supervisor client boxie-supervisor clientAuth 0
ui/ui-client client ui clientAuth 1000
operator/operator client operator clientAuth 1000'
if [[ -d $root ]]; then
    [[ -f $root/complete ]] || { echo 'Partial certificates; restore the complete set.' >&2; exit 1; }
    while read -r identity _; do
        openssl x509 -checkend 604800 -noout -in "$root/$identity.pem" >/dev/null || { echo 'Certificate renewal required.' >&2; exit 1; }
        [[ -s $root/$identity.key ]] || exit 1
    done <<< "$certificates"
    exit 0
fi
install -d -m 0700 "$(dirname "$root")"
staging=$(mktemp -d "${root}.new.XXXXXX")
trap 'rm -rf "$staging"' EXIT
install -d -m 0700 "$staging/ca"
for name in frontend internode client; do
    openssl req -x509 -newkey rsa:3072 -nodes -days 365 -subj "/CN=Boxie $name CA" \
        -keyout "$staging/ca/$name.key" -out "$staging/ca/$name.pem" >/dev/null 2>&1
done
while read -r identity issuer san usage owner; do
    directory="$staging/${identity%/*}"
    name=${identity##*/}
    if [[ ! -d $directory ]]; then
        install -d -m 0755 "$directory"
        cp "$staging/ca/frontend.pem" "$directory/frontend-ca.pem"
    fi
    openssl req -newkey rsa:2048 -nodes -subj "/CN=$name" -keyout "$staging/$identity.key" -out "$staging/ca/$name.csr" >/dev/null 2>&1
    printf 'subjectAltName=DNS:%s\nextendedKeyUsage=%s\nbasicConstraints=CA:FALSE\n' "$san" "$usage" > "$staging/ca/$name.ext"
    openssl x509 -req -in "$staging/ca/$name.csr" -CA "$staging/ca/$issuer.pem" -CAkey "$staging/ca/$issuer.key" \
        -CAcreateserial -days 90 -extfile "$staging/ca/$name.ext" -out "$staging/$identity.pem" >/dev/null 2>&1
    chown "${2:-$owner}:${3:-$owner}" "$staging/$identity.key"
done <<< "$certificates"
for name in internode client; do cp "$staging/ca/$name.pem" "$staging/server/$name-ca.pem"; done
find "$staging" -name '*.pem' -exec chmod 0644 {} +
# The enclosing directory is traversable for the numeric readers; CA directory is private.
chmod 0755 "$staging"
touch "$staging/complete"
mv "$staging" "$root"
