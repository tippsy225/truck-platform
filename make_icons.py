import os
import struct
import zlib

GREEN = (28, 107, 74)
WHITE = (255, 255, 255)
AMBER = (245, 168, 0)


def color_at(u, v):
    # The picture lives in the central 64 percent, which keeps it safe on rounded phone icons.
    x = (u - 0.18) / 0.64
    y = (v - 0.18) / 0.64
    if 0 <= x <= 1 and 0 <= y <= 1:
        if (x - 0.72) ** 2 + (y - 0.28) ** 2 <= 0.17 ** 2:
            return AMBER
        if 0.62 <= y <= 0.74 and 0.04 <= x <= 0.96 and ((x - 0.04) % 0.24) < 0.15:
            return WHITE
    return GREEN


def render(size, factor=2):
    rows = []
    for py in range(size):
        row = bytearray()
        for px in range(size):
            r = g = b = 0
            for sy in range(factor):
                for sx in range(factor):
                    c = color_at((px + (sx + .5) / factor) / size, (py + (sy + .5) / factor) / size)
                    r += c[0]
                    g += c[1]
                    b += c[2]
            n = factor * factor
            row += bytes((r // n, g // n, b // n))
        rows.append(bytes(row))
    return rows


def write_png(path, size):
    raw = b''.join(b'\x00' + row for row in render(size))

    def chunk(tag, data):
        body = tag + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)

    header = struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) +
           chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(png)


if __name__ == '__main__':
    folder = os.path.join('accounts', 'static', 'accounts', 'icons')
    os.makedirs(folder, exist_ok=True)
    for size in (192, 512):
        write_png(os.path.join(folder, f'icon-{size}.png'), size)
        print(f'Wrote icon-{size}.png')