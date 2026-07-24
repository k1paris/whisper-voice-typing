#!/bin/bash
# Запускать БЕЗ sudo: ./whisper_daemon.sh
# Требуется: $USER в группе input (sudo usermod -aG input $USER + релогин)

AUDIO_FILE="/tmp/whisper_caps.wav"
SERVER_URL="http://127.0.0.1:8090/inference"
DEVICE="/dev/input/event3"

command -v evtest >/dev/null || { echo "нужен evtest: sudo apt install evtest"; exit 1; }
command -v xdotool >/dev/null || { echo "нужен xdotool: sudo apt install xdotool"; exit 1; }
command -v xclip >/dev/null || { echo "нужен xclip: sudo apt install xclip"; exit 1; }
command -v parec >/dev/null || { echo "нужен parec: sudo apt install pulseaudio-utils"; exit 1; }

if ! curl -s -o /dev/null "http://127.0.0.1:8090"; then
    echo "⚠️  whisper-server не отвечает на 8090"
    exit 1
fi

pkill -x parec 2>/dev/null

echo "Слушаем $DEVICE. Удерживай ПРАВЫЙ Ctrl для записи..."

RECORDING=0

evtest "$DEVICE" | while read -r line; do

    if [[ "$line" == *"code 97 (KEY_RIGHTCTRL)"* && "$line" == *"value 1"* ]]; then
        if [ "$RECORDING" -eq 0 ]; then
            RECORDING=1
            clear
            echo "🎤 Запись пошла... (говори)"
            rm -f "$AUDIO_FILE"
            parec --rate=16000 --channels=1 --format=s16le --file-format=wav \
                "$AUDIO_FILE" >/tmp/rec_debug.log 2>&1 &
        fi
    fi

    if [[ "$line" == *"code 97 (KEY_RIGHTCTRL)"* && "$line" == *"value 0"* ]]; then
        if [ "$RECORDING" -eq 1 ]; then
            RECORDING=0
            sleep 0.9
            pkill -INT -x parec 2>/dev/null
            sleep 0.2

            if [ ! -s "$AUDIO_FILE" ]; then
                echo "❌ Файл записи пустой"
                continue
            fi

            RESULT=$(curl -s "$SERVER_URL" -F file=@"$AUDIO_FILE" -F language=ru -F response_format=text)
            RESULT=$(printf '%s' "$RESULT" | tr -d '\n\r')
            RESULT="${RESULT#"${RESULT%%[![:space:]]*}"}"
            RESULT="${RESULT%"${RESULT##*[![:space:]]}"}"

            echo "--- Результат ---"
            echo "$RESULT"
            echo "-----------------"

            if [ -n "$RESULT" ]; then
                printf '%s' "$RESULT" | xclip -selection clipboard
                xdotool key --clearmodifiers ctrl+v
            fi

            echo -e "\nГотов (зажми Правый Ctrl для новой записи)..."
        fi
    fi
done