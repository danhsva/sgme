#!/usr/bin/env python3
"""
SGME - Reduz as fotos JÁ enviadas (anexos grandes de O.S. antigas).
Para cada foto > 500 KB ligada a uma O.S.: gera uma versão otimizada (lado maior 1600 px, JPEG 80%, sem GPS),
atualiza a O.S. para apontar para ela e MOVE o original para dados/uploads_originais/ (nada é apagado).
Uso:
  venv/bin/python reduzir_anexos_existentes.py              # só simula
  venv/bin/python reduzir_anexos_existentes.py --executar   # aplica
"""
import argparse, os, shutil, sqlite3, sys, uuid
from PIL import Image, ImageOps

DADOS = os.environ.get('SGME_DADOS', '/var/lib/sgme' if os.path.exists('/var/lib/sgme') else os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'dados')))
DB, UPLOADS = os.path.join(DADOS, 'sistema.db'), os.path.join(DADOS, 'uploads')
ORIGINAIS = os.path.join(DADOS, 'uploads_originais')
LADO_MAX, MIN_BYTES = 1600, 500 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000


def otimizar(origem, destino):
    img = Image.open(origem)
    if img.format == 'JPEG':
        img.draft('RGB', (LADO_MAX, LADO_MAX))
    img = ImageOps.exif_transpose(img)
    img.thumbnail((LADO_MAX, LADO_MAX))
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGBA')
        fundo = Image.new('RGB', img.size, (255, 255, 255))
        fundo.paste(img, mask=img.split()[-1])
        img = fundo
    else:
        img = img.convert('RGB')
    img.save(destino, 'JPEG', quality=80, optimize=True)


def ja_otimizada(caminho):
    """JPEG que já cabe no limite de 1600 px (feito por este script ou pelo upload otimizado): não refazer."""
    try:
        with Image.open(caminho) as im:
            return im.format == 'JPEG' and max(im.size) <= LADO_MAX
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--executar', action='store_true')
    a = ap.parse_args()
    conn = sqlite3.connect(DB, timeout=30)
    refs = {r[0] for r in conn.execute("SELECT arquivo_conclusao FROM ordens_servico WHERE arquivo_conclusao IS NOT NULL")}
    grandes = [(n, os.path.getsize(os.path.join(UPLOADS, n))) for n in sorted(os.listdir(UPLOADS))
               if n.lower().endswith(('.jpg', '.jpeg', '.png')) and os.path.getsize(os.path.join(UPLOADS, n)) > MIN_BYTES
               and not ja_otimizada(os.path.join(UPLOADS, n))]
    alvo = [(n, s) for n, s in grandes if n in refs]
    orfas = [(n, s) for n, s in grandes if n not in refs]
    print(f'Fotos grandes ligadas a O.S.: {len(alvo)} ({sum(s for _, s in alvo) / 1e6:.1f} MB)')
    print(f'Fotos grandes sem O.S. (não serão tocadas): {len(orfas)}')
    if not a.executar:
        print('\n(simulação) Nada foi alterado. Para aplicar: --executar')
        return
    os.makedirs(ORIGINAIS, exist_ok=True)
    antes = depois = feitos = 0
    for nome, tam in alvo:
        origem, novo = os.path.join(UPLOADS, nome), uuid.uuid4().hex + '.jpg'
        destino = os.path.join(UPLOADS, novo)
        try:
            otimizar(origem, destino)
            novo_tam = os.path.getsize(destino)
            if novo_tam >= tam:
                os.remove(destino)
                continue
            conn.execute('UPDATE ordens_servico SET arquivo_conclusao=? WHERE arquivo_conclusao=?', (novo, nome))
            conn.commit()
            shutil.move(origem, os.path.join(ORIGINAIS, nome))
            antes, depois, feitos = antes + tam, depois + novo_tam, feitos + 1
        except Exception as e:
            print(f'  ignorado {nome}: {e}')
            if os.path.exists(destino):
                os.remove(destino)
    print(f'\nConcluído: {feitos} foto(s). {antes / 1e6:.1f} MB -> {depois / 1e6:.1f} MB.')
    print(f'Originais guardados em {ORIGINAIS} (pode apagar depois de conferir).')


if __name__ == '__main__':
    main()
