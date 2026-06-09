"""Gera as imagens (PNG + SVG) dos diagramas da aplicação DevBook.

Uso:  python docs/gerar_diagramas.py

Não requer Java/Graphviz/PlantUML — usa apenas matplotlib.
Os diagramas refletem o modelo atual (com Reações, Notificações e Mensagens).
"""
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Ellipse, FancyArrowPatch

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

PRIMARY = '#24bfa5'
DARK = '#0f172a'
HEADER_BG = '#24bfa5'
BOX_BG = '#ffffff'
BORDER = '#0f172a'
LINE = '#475569'


# --------------------------------------------------------------------------
# Diagrama de Classes
# --------------------------------------------------------------------------
def draw_class(ax, x, y, w, name, attrs, methods):
    """Desenha uma classe UML (nome / atributos / métodos). (x, y) = canto sup. esq.
    Retorna dict com bordas para conectar relações."""
    line_h = 0.40
    header_h = 0.70
    pad = 0.18
    n_lines = len(attrs) + len(methods)
    body_h = max(n_lines * line_h + 2 * pad, 0.5)
    sep = 0.0  # separador entre atributos e métodos é desenhado depois
    total_h = header_h + body_h
    top = y
    bottom = y - total_h

    # corpo
    ax.add_patch(FancyBboxPatch(
        (x, bottom), w, total_h,
        boxstyle='square,pad=0', linewidth=1.4,
        edgecolor=BORDER, facecolor=BOX_BG, zorder=2,
    ))
    # cabeçalho
    ax.add_patch(FancyBboxPatch(
        (x, top - header_h), w, header_h,
        boxstyle='square,pad=0', linewidth=1.4,
        edgecolor=BORDER, facecolor=HEADER_BG, zorder=3,
    ))
    ax.text(x + w / 2, top - header_h / 2, name, ha='center', va='center',
            fontsize=11, fontweight='bold', color='white', zorder=4)

    # atributos
    cy = top - header_h - pad - line_h / 2
    for a in attrs:
        ax.text(x + pad, cy, a, ha='left', va='center', fontsize=8.2,
                color=DARK, zorder=4)
        cy -= line_h
    # separador
    if methods:
        sep_y = cy + line_h / 2
        ax.plot([x, x + w], [sep_y, sep_y], color=BORDER, linewidth=1.0, zorder=4)
    for m in methods:
        ax.text(x + pad, cy, m, ha='left', va='center', fontsize=8.2,
                color='#1f2937', zorder=4, style='italic')
        cy -= line_h

    return {
        'name': name, 'x': x, 'y': bottom, 'w': w, 'h': total_h,
        'left': (x, bottom + total_h / 2),
        'right': (x + w, bottom + total_h / 2),
        'top': (x + w / 2, top),
        'bottom': (x + w / 2, bottom),
        'cx': x + w / 2, 'cy': bottom + total_h / 2,
    }


def rel(ax, p1, p2, label='', m1='', m2='', dashed=False):
    style = (0, (5, 4)) if dashed else 'solid'
    ax.add_patch(FancyArrowPatch(
        p1, p2, arrowstyle='-', linewidth=1.3, color=LINE,
        linestyle=style, zorder=1, shrinkA=2, shrinkB=2,
    ))
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    if label:
        ax.text(mx, my + 0.16, label, ha='center', va='bottom', fontsize=7.6,
                color='#334155',
                bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=0.85),
                zorder=5)
    if m1:
        ax.text(p1[0], p1[1], m1, ha='center', va='center', fontsize=7,
                color='#0f766e', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.1', fc='#ecfeff', ec='none'), zorder=6)
    if m2:
        ax.text(p2[0], p2[1], m2, ha='center', va='center', fontsize=7,
                color='#0f766e', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.1', fc='#ecfeff', ec='none'), zorder=6)


def class_diagram():
    fig, ax = plt.subplots(figsize=(15, 11))
    ax.set_xlim(0, 30)
    ax.set_ylim(0, 22)
    ax.axis('off')
    ax.set_title('DevBook — Diagrama de Classes', fontsize=16, fontweight='bold',
                 color=DARK, pad=14)

    user = draw_class(ax, 1.0, 20.5, 8.2, 'User',
        ['+ id: int', '+ name: str', '+ mail: str (unique)',
         '+ password: str', '+ avatar_filename: str'],
        ['+ follow(user)', '+ unfollow(user)', '+ is_following(user): bool',
         '+ followers_count', '+ following_count', '+ unread_notifications_count'])

    post = draw_class(ax, 20.0, 20.5, 8.6, 'Post',
        ['+ id: int', '+ body: text', '+ created_at: datetime',
         '+ author_id: FK -> User', '+ parent_id: FK -> Post'],
        ['+ reaction_by(user)', '+ user_reaction_type(user)',
         '+ is_liked_by(user): bool', '+ like_count',
         '+ reaction_summary', '+ comment_count'])

    reaction = draw_class(ax, 11.0, 12.0, 8.0, 'Reaction',
        ['+ id: int', '+ type: str', '+ created_at: datetime',
         '+ user_id: FK -> User', '+ post_id: FK -> Post'],
        ['+ emoji', 'unique(user_id, post_id)'])

    comment = draw_class(ax, 21.0, 11.5, 8.2, 'Comment',
        ['+ id: int', '+ body: text', '+ created_at: datetime',
         '+ author_id: FK -> User', '+ post_id: FK -> Post'],
        [])

    notif = draw_class(ax, 0.6, 9.5, 9.0, 'Notification',
        ['+ id: int', '+ type: str  (reaction|comment|share|follow)',
         '+ is_read: bool', '+ created_at: datetime',
         '+ recipient_id: FK -> User', '+ actor_id: FK -> User',
         '+ post_id: FK -> Post (opcional)'],
        [])

    message = draw_class(ax, 1.0, 1.5, 8.6, 'Message',
        ['+ id: int', '+ body: text', '+ is_read: bool',
         '+ created_at: datetime', '+ sender_id: FK -> User',
         '+ recipient_id: FK -> User'],
        [])

    # Relações
    rel(ax, user['right'], post['left'], 'cria (author)', '1', '0..*')
    rel(ax, user['bottom'], reaction['top'], 'faz', '1', '0..*')
    rel(ax, post['bottom'], reaction['right'], 'recebe', '1', '0..*')
    rel(ax, post['bottom'], comment['top'], 'tem', '1', '0..*')
    rel(ax, (user['x'] + user['w'] * 0.25, user['y']),
        (comment['x'], comment['y'] + comment['h'] * 0.5),
        'escreve', '1', '0..*')
    rel(ax, user['bottom'], notif['top'], 'recebe / dispara', '1', '0..*')
    rel(ax, (post['x'], post['y'] + 0.4), (notif['right']), 'refere', '0..1', '0..*', dashed=True)
    rel(ax, (user['x'] + 1.5, user['y']), message['top'], 'envia / recebe', '1', '0..*')

    # Auto-relação followers (User <-> User)
    ux, uy = user['x'], user['y'] + user['h']
    ax.add_patch(FancyArrowPatch(
        (user['x'] + user['w'] * 0.6, uy), (user['x'] + user['w'] * 0.9, uy),
        connectionstyle='arc3,rad=-1.6', arrowstyle='-', linewidth=1.3,
        color=LINE, zorder=1))
    ax.text(user['x'] + user['w'] * 0.75, uy + 1.15, 'segue (followers)  * .. *',
            ha='center', fontsize=7.6, color='#334155')

    # Auto-relação repost (Post parent/shares) — laço no topo, simétrico ao de followers
    pty = post['y'] + post['h']
    ax.add_patch(FancyArrowPatch(
        (post['x'] + post['w'] * 0.1, pty), (post['x'] + post['w'] * 0.4, pty),
        connectionstyle='arc3,rad=-1.6', arrowstyle='-', linewidth=1.3,
        color=LINE, zorder=1))
    ax.text(post['x'] + post['w'] * 0.25, pty + 1.15,
            'repost (parent / shares)  0..1 .. *', ha='center', fontsize=7.6,
            color='#334155')

    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'diagrama-de-classes.png'), dpi=160,
                bbox_inches='tight', facecolor='white')
    fig.savefig(os.path.join(OUT_DIR, 'diagrama-de-classes.svg'),
                bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print('OK: diagrama-de-classes.png / .svg')


# --------------------------------------------------------------------------
# Diagrama de Casos de Uso
# --------------------------------------------------------------------------
def draw_actor(ax, x, y, name):
    r = 0.32
    ax.add_patch(plt.Circle((x, y), r, fill=False, lw=1.6, color=BORDER, zorder=4))
    ax.plot([x, x], [y - r, y - r - 0.9], color=BORDER, lw=1.6, zorder=4)       # tronco
    ax.plot([x - 0.55, x + 0.55], [y - r - 0.35, y - r - 0.35], color=BORDER, lw=1.6, zorder=4)  # braços
    ax.plot([x, x - 0.45], [y - r - 0.9, y - r - 1.6], color=BORDER, lw=1.6, zorder=4)  # perna
    ax.plot([x, x + 0.45], [y - r - 0.9, y - r - 1.6], color=BORDER, lw=1.6, zorder=4)
    ax.text(x, y - r - 2.0, name, ha='center', va='top', fontsize=9.5,
            fontweight='bold', color=DARK, zorder=4)
    return (x, y - r - 0.45)  # ponto de conexão (no tronco)


def draw_uc(ax, x, y, label, w=3.1, h=1.0):
    ax.add_patch(Ellipse((x, y), w, h, facecolor=BOX_BG, edgecolor=PRIMARY,
                         lw=1.5, zorder=3))
    ax.text(x, y, label, ha='center', va='center', fontsize=8.0, color=DARK,
            zorder=4, wrap=True)
    return {'left': (x - w / 2, y), 'right': (x + w / 2, y), 'c': (x, y)}


def use_case_diagram():
    fig, ax = plt.subplots(figsize=(15, 11))
    ax.set_xlim(0, 30)
    ax.set_ylim(0, 24)
    ax.axis('off')
    ax.set_title('DevBook — Diagrama de Casos de Uso', fontsize=16,
                 fontweight='bold', color=DARK, pad=14)

    # Sistema
    ax.add_patch(FancyBboxPatch((7.0, 1.0), 16.5, 21.5, boxstyle='round,pad=0.1',
                 linewidth=1.6, edgecolor=BORDER, facecolor='#f8fafc', zorder=0))
    ax.text(15.25, 22.0, 'DevBook', ha='center', fontsize=12, fontweight='bold',
            color=PRIMARY, zorder=1)

    # Atores
    visit_pt = draw_actor(ax, 2.5, 18.0, 'Visitante')
    user_pt = draw_actor(ax, 2.5, 8.5, 'Usuário\nAutenticado')
    # herança visitante <- usuário
    ax.add_patch(FancyArrowPatch((2.5, 5.8), (2.5, 15.3),
                 arrowstyle='-|>', mutation_scale=14, linewidth=1.2,
                 color=LINE, linestyle=(0, (4, 3)), zorder=2))
    ax.text(3.0, 11.0, 'é um', fontsize=7.5, color='#334155', rotation=90)

    # Casos do visitante
    uc_reg = draw_uc(ax, 10.0, 19.8, 'Registrar conta')
    uc_log = draw_uc(ax, 10.0, 18.0, 'Fazer login')

    # Casos do usuário autenticado
    col1_x = 11.0
    col2_x = 19.5
    ys = [15.8, 13.9, 12.0, 10.1, 8.2, 6.3, 4.4, 2.6]
    uc_feed = draw_uc(ax, col1_x, ys[0], 'Ver feed\n(global / seguindo)')
    uc_busca = draw_uc(ax, col1_x, ys[1], 'Buscar publicações')
    uc_pub = draw_uc(ax, col1_x, ys[2], 'Publicar post')
    uc_edit = draw_uc(ax, col1_x, ys[3], 'Editar post')
    uc_react = draw_uc(ax, col1_x, ys[4], 'Reagir\n(like/love/haha...)')
    uc_coment = draw_uc(ax, col1_x, ys[5], 'Comentar')
    uc_share = draw_uc(ax, col1_x, ys[6], 'Partilhar (repost)')
    uc_follow = draw_uc(ax, col1_x, ys[7], 'Seguir / Deixar de seguir')

    uc_perfil = draw_uc(ax, col2_x, ys[1], 'Atualizar perfil / avatar')
    uc_verperfil = draw_uc(ax, col2_x, ys[2], 'Ver perfil de usuário')
    uc_notif = draw_uc(ax, col2_x, ys[3], 'Ver notificações')
    uc_conv = draw_uc(ax, col2_x, ys[4], 'Ver conversas')
    uc_msg = draw_uc(ax, col2_x, ys[5], 'Enviar mensagem privada')
    uc_logout = draw_uc(ax, col2_x, ys[6], 'Fazer logout')

    def link(actor_pt, uc):
        ax.add_patch(FancyArrowPatch(actor_pt, uc['left'], arrowstyle='-',
                     linewidth=1.0, color=LINE, zorder=1, shrinkB=2))

    # Visitante
    for uc in (uc_reg, uc_log):
        link(visit_pt, uc)
    # Usuário autenticado
    for uc in (uc_feed, uc_busca, uc_pub, uc_edit, uc_react, uc_coment,
               uc_share, uc_follow, uc_perfil, uc_verperfil, uc_notif,
               uc_conv, uc_msg, uc_logout):
        link(user_pt, uc)

    def inc(a, b, txt='<<include>>'):
        ax.add_patch(FancyArrowPatch(a['right'], b['left'], arrowstyle='-|>',
                     mutation_scale=12, linewidth=1.0, color='#94a3b8',
                     linestyle=(0, (3, 3)), zorder=1))
        mx, my = (a['right'][0] + b['left'][0]) / 2, (a['right'][1] + b['left'][1]) / 2
        ax.text(mx, my + 0.15, txt, fontsize=6.5, color='#64748b', ha='center')

    # Ações que geram notificações
    inc(uc_react, uc_notif)
    inc(uc_coment, uc_notif)
    inc(uc_follow, uc_notif)
    inc(uc_conv, uc_msg)

    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'diagrama-casos-de-uso.png'), dpi=160,
                bbox_inches='tight', facecolor='white')
    fig.savefig(os.path.join(OUT_DIR, 'diagrama-casos-de-uso.svg'),
                bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print('OK: diagrama-casos-de-uso.png / .svg')


if __name__ == '__main__':
    class_diagram()
    use_case_diagram()
    print('Imagens geradas em:', OUT_DIR)
