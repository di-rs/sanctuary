#!/bin/sh
# The CA stays on the host. Each service receives just its leaf and the public CA.
set -eu
umask 077
dir="${SANCTUARY_STATE:-/var/lib/sanctuary}/tls"
mkdir -p "$dir"
if [ ! -s "$dir/ca.key" ]; then
    openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$dir/ca.key"
fi
if [ ! -s "$dir/ca.pem" ]; then
    openssl req -new -x509 -sha256 -days 3650 -key "$dir/ca.key" -subj /CN=Sanctuary-CA -out "$dir/ca.pem"
fi
for leaf in temporal api worker operator ui; do
    dest="$dir/$leaf"
    mkdir -p "$dest"
    if [ -s "$dest/cert.pem" ] && openssl x509 -checkend 2592000 -noout -in "$dest/cert.pem" >/dev/null; then
        continue
    fi
    stage=$(mktemp -d "$dir/.issue.XXXXXXXX")
    openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj "/CN=$leaf" -keyout "$stage/key.pem" -out "$stage/request"
    printf 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=clientAuth\n' > "$stage/extensions"
    if [ "$leaf" = temporal ]; then
        printf 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=clientAuth,serverAuth\nsubjectAltName=DNS:temporal\n' > "$stage/extensions"
    fi
    serial=$(openssl rand -hex 16)
    openssl x509 -req -sha256 -days 365 -in "$stage/request" -CA "$dir/ca.pem" -CAkey "$dir/ca.key" -set_serial "0x$serial" -extfile "$stage/extensions" -out "$stage/cert.pem"
    if [ -s "$dest/cert.pem" ]; then
        mkdir -p "$dir/restarts"
        case "$leaf" in
            api|worker) touch "$dir/restarts/boxie" ;;
            ui|temporal) touch "$dir/restarts/temporal" ;;
        esac
    fi
    cp "$dir/ca.pem" "$dest/ca.pem"
    mv "$stage/key.pem" "$stage/cert.pem" "$dest/"
    chmod 755 "$dest"
    # The host parent is root-only. Only the named service receives the directory.
    chmod 444 "$dest/"*.pem
    rm -f "$stage/request" "$stage/extensions"
    rmdir "$stage"
done
