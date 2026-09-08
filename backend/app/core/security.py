"""Хеширование паролей и выпуск токенов сессии.

Хеширование — scrypt из стандартной библиотеки, без внешних зависимостей.
Выбор осознанный: bcrypt и argon2 тянут за собой пакеты с бинарными
колёсами, которые надо собирать под каждую платформу, а установка Aurum-Ex
должна подниматься одной командой на чужом сервере. scrypt при этом
memory-hard — подбор на видеокартах упирается в память, а не в скорость
перебора, чего от алгоритма для пароля и требуется.

Формат хранимой строки самодостаточен:

    scrypt$16384$8$1$<соль base64>$<хеш base64>

Параметры лежат внутри неё, поэтому их можно ужесточить в будущем, не
ломая уже сохранённые пароли: проверка читает параметры из самой строки, а
не из констант ниже. Пароль, проверенный по устаревшим параметрам, при
следующем успешном входе перехешируется (см. needs_rehash).
"""
import base64
import hashlib
import hmac
import secrets

# Параметры scrypt для новых хешей. n — счётчик итераций и объём памяти
# (16384 × 8 × 128 байт ≈ 16 МБ на проверку), r и p — рекомендованные
# значения RFC 7914. Хватает, чтобы перебор был дорогим, и не настолько
# много, чтобы вход тормозил на слабом VPS.
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32

_PREFIX = "scrypt"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def hash_password(password: str) -> str:
    """Возвращает строку вида scrypt$n$r$p$соль$хеш."""
    salt = secrets.token_bytes(_SALT_BYTES)
    key = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_KEY_BYTES
    )
    return f"{_PREFIX}${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(key)}"


def verify_password(password: str, stored: str) -> bool:
    """Проверяет пароль по сохранённой строке.

    Сравнение идёт через compare_digest: обычное == выходит из цикла на
    первом несовпавшем байте, и по времени ответа можно подбирать хеш
    посимвольно. Битая или чужого формата строка считается непрошедшей
    проверку, а не поводом для исключения — иначе повреждённая запись в базе
    превращалась бы в 500 на экране входа.
    """
    try:
        prefix, n_raw, r_raw, p_raw, salt_raw, key_raw = stored.split("$")
        if prefix != _PREFIX:
            return False
        expected = _unb64(key_raw)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt_raw),
            n=int(n_raw),
            r=int(r_raw),
            p=int(p_raw),
            dklen=len(expected),
        )
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(stored: str) -> bool:
    """Правда, если хеш создан со старыми параметрами и его стоит обновить.

    Перехеширование делается при успешном входе — только там приложение
    держит пароль в открытом виде и может пересчитать хеш."""
    try:
        prefix, n_raw, r_raw, p_raw, _, _ = stored.split("$")
    except ValueError:
        return True
    if prefix != _PREFIX:
        return True
    return (int(n_raw), int(r_raw), int(p_raw)) != (_SCRYPT_N, _SCRYPT_R, _SCRYPT_P)


# Слоги для случайного логина: согласная-гласная-согласная. Такой набор
# читается и диктуется вслух, в отличие от строки случайных символов, а
# стойкость набирает длиной.
_SYLLABLE_CONSONANTS = "bvgdkmnprstf"
_SYLLABLE_VOWELS = "aeiouy"


def new_random_username(syllables: int = 3) -> str:
    """Случайный логин вида «kotimeraved».

    Смысл ограниченный, но реальный: перебор упирается в блокировку по
    учётной записи, и угадывать приходится обе половины, а не только пароль.
    Как единственная защита это ничего не стоит — как дополнительный барьер
    поверх пароля и блокировки работает.
    """
    return "".join(
        secrets.choice(_SYLLABLE_CONSONANTS) + secrets.choice(_SYLLABLE_VOWELS) + secrets.choice(_SYLLABLE_CONSONANTS)
        for _ in range(syllables)
    )


def new_session_token() -> str:
    """Секрет сессии, который уезжает в куку браузера. 32 случайных байта в
    URL-безопасном виде — угадать нельзя, подписывать нечем и незачем:
    сессия проверяется по своей записи в базе."""
    return secrets.token_urlsafe(32)


def session_token_fingerprint(token: str) -> str:
    """Отпечаток токена для хранения в базе.

    В таблицу кладётся не сам токен, а его SHA-256: у того, кто прочитал
    базу, не окажется на руках готовых ключей от активных сессий. Соль здесь
    не нужна — токен и так 256 бит случайности, словарём его не берут."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()
