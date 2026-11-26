#!/usr/bin/env bash
set -Eeuo pipefail

RAIZ="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$RAIZ"

VERSION="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
DIST="$RAIZ/dist"
PKG="$RAIZ/paquete_control_voz"
rm -rf "${DIST:?}" "${PKG:?}/usr"
mkdir -p "$DIST" "$PKG/DEBIAN" "$PKG/usr/bin" "$PKG/usr/share/control-voz" "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/scalable/apps" "$PKG/usr/share/doc/control-voz" "$PKG/usr/share/man/man1" "$PKG/usr/share/metainfo"

cp -r src/control_voz "$PKG/usr/share/control-voz/"
find "$PKG/usr/share/control-voz" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$PKG/usr/share/control-voz" -name '*.pyc' -delete
cat > "$PKG/usr/bin/control-voz" <<'SH'
#!/usr/bin/env bash
export PYTHONPATH="/usr/share/control-voz${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m control_voz.app "$@"
SH
chmod 0755 "$PKG/usr/bin/control-voz"
install -m 0644 assets/control-voz.desktop "$PKG/usr/share/applications/control-voz.desktop"
install -m 0644 assets/control-voz.svg "$PKG/usr/share/icons/hicolor/scalable/apps/control-voz.svg"
install -m 0644 assets/control-voz-off.svg "$PKG/usr/share/icons/hicolor/scalable/apps/control-voz-off.svg"
install -m 0644 assets/control-voz-command.svg "$PKG/usr/share/icons/hicolor/scalable/apps/control-voz-command.svg"
install -m 0644 assets/control-voz-dictation.svg "$PKG/usr/share/icons/hicolor/scalable/apps/control-voz-dictation.svg"
install -m 0644 LICENSE "$PKG/usr/share/doc/control-voz/copyright"
install -m 0644 README.md "$PKG/usr/share/doc/control-voz/README.md"
gzip -n -9 -c assets/control-voz.1 > "$PKG/usr/share/man/man1/control-voz.1.gz"
gzip -n -9 -c debian/changelog > "$PKG/usr/share/doc/control-voz/changelog.gz"
install -m 0644 assets/control-voz.appdata.xml "$PKG/usr/share/metainfo/com.elabuelazotech.controlvoz.metainfo.xml"

cat > "$PKG/DEBIAN/control" <<CTRL
Package: control-voz
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-gi, gir1.2-gtk-3.0, gir1.2-xapp-1.0, gir1.2-keybinder-3.0, xdotool, pulseaudio-utils
Recommends: python3-vosk
Maintainer: Angelino Santana (El Abuelazo Tech) <elabuelazotech@gmail.com>
Description: Escúchame: dictado y control por voz para Linux Mint Cinnamon
 Aplicación con indicador de panel para comandos de voz y dictado.
 Permite cambiar entre apagado, control y dictado, y configurar comandos.
CTRL

find "$PKG/usr" -type d -exec chmod 0755 {} +
find "$PKG/usr" -type f -exec chmod 0644 {} +
chmod 0755 "$PKG/usr/bin/control-voz"

dpkg-deb --build --root-owner-group "$PKG" "$DIST/control-voz_${VERSION}_all.deb"
printf 'Paquete: %s\n' "$DIST/control-voz_${VERSION}_all.deb"
