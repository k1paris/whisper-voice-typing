#!/bin/bash
# Whisper Voice Typing — Installer
# Устанавливает зависимости, создаёт .desktop и автозапуск.
# Запуск: bash install.sh
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_EXEC="python3 ${APP_DIR}/whisper_app.py"
APP_ICON="${APP_DIR}/icons/whisper-idle.svg"
DESKTOP_NAME="whisper-voice.desktop"

echo "══════════════════════════════════════════════"
echo "  Whisper Voice Typing — Установка"
echo "══════════════════════════════════════════════"
echo ""

# ── 1. System dependencies ──
echo "📦 Устанавливаем системные зависимости…"
sudo apt install -y evtest xdotool xclip pulseaudio-utils
echo ""

# ── 2. Check Python + GTK ──
echo "🔍 Проверяем Python3 + GTK3 + AppIndicator…"
python3 -c "
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, AyatanaAppIndicator3
print('   ✅ Python3 + GTK3 + AppIndicator — OK')
" || {
    echo "   ❌ Не удалось импортировать GTK/AppIndicator."
    echo "   Попробуйте: sudo apt install python3-gi gir1.2-ayatanaappindicator3-0.1"
    exit 1
}
echo ""

# ── 3. Data directory ──
mkdir -p ~/.local/share/whisper-app
echo "📁 Директория данных: ~/.local/share/whisper-app/"

# ── 4. Desktop entry (app menu) ──
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/${DESKTOP_NAME} << EOF
[Desktop Entry]
Type=Application
Name=Whisper Voice
GenericName=Voice Typing
Comment=Голосовой ввод текста через Whisper AI
Exec=${APP_EXEC}
Icon=${APP_ICON}
Terminal=false
Categories=Utility;Audio;Accessibility;
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF
echo "🖥️  Ярлык в меню приложений: создан"

# ── 5. Autostart ──
mkdir -p ~/.config/autostart
cp ~/.local/share/applications/${DESKTOP_NAME} \
   ~/.config/autostart/${DESKTOP_NAME}
echo "🚀 Автозапуск при входе: включен"

# ── 6. Input group ──
if ! groups | grep -q '\binput\b'; then
    echo ""
    echo "⚠️  Добавляем пользователя в группу input (для evtest)…"
    sudo usermod -aG input "$USER"
    echo "   ⚠️  Нужно перелогиниться для применения!"
else
    echo "👤 Группа input: OK"
fi

echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ Установка завершена!"
echo ""
echo "  Запуск:  python3 ${APP_DIR}/whisper_app.py"
echo "  Или:     через меню приложений → Whisper Voice"
echo "  Авто:    при каждом входе в систему"
echo "══════════════════════════════════════════════"
