/*
 * target_game.c (v3) — тестовая мишень «каждый уровень имеет значение».
 *
 * Цепочка: каждый уровень показывает СВОЁ число, финальный уровень — деньги.
 *
 *   target_game.exe+9080 (.bss, g_game)   — СТАТИЧЕСКИЙ ЯКОРЬ
 *     +0x00 → Game   Game.Value = 1111.0  — уровень 1
 *       +0x10 → L1     L1.Value  = 2222.0  — уровень 2
 *         +0x10 → L2   L2.Value  = 3333.0  — уровень 3
 *           +0x10 → L3 L3.Value  = ДЕНЬГИ   — уровень 4 (официальные деньги)
 *             +0x10 → L4 L4.Value  = ДЕНЬГИ   — зеркало (обновляется тиком)
 *
 * Структура уровня: +0x00 double Value, +0x10 Next, +0x18 double Marker.
 * GC каждые 15 с пересоздаёт L1..L4 (адреса меняются, значения сохраняются).
 *
 * Матрица ручных pointer-записей в CE (Pointer, база target_game.exe+9080,
 * офсеты сверху вниз, все в HEX) — каждая показывает СВОЁ число:
 *   {0}                              → 1111
 *   {0, 0}                           → 1111   (Game.Value через доп. deref)
 *   {0, 10, 0}                       → 2222
 *   {0, 10, 10, 0}                   → 3333
 *   {0, 10, 10, 10, 0}               → ДЕНЬГИ
 *   {0, 10, 10, 10, 10, 0}           → ДЕНЬГИ (L4)
 * Если какая-то строка даёт «??» на записи, созданной руками, — это кварк
 * сборки CE на этой глубине, а не баг инструмента.
 *
 * Сборка (x64, -O0 обязателен):
 *   gcc -O0 -static -o target_game.exe target_game.c
 *
 * Клавиши: [пробел] +100 денег, [g] GC сейчас, [p] печать цепочки, [q] выход.
 * Аргументы: target_game.exe [money_ms] [gc_ms]   (по умолчанию 2000 и 15000)
 */

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <conio.h>
#include <stddef.h>

typedef struct Level {             /* transient: пересоздаётся GC */
    double        Value;           /* +0x00 значение уровня        */
    char          pad[0x08];       /* +0x08                        */
    struct Level* Next;            /* +0x10 следующий уровень      */
    double        Marker;          /* +0x18 маркер уровня          */
} Level;

typedef struct Game {              /* живёт от старта до выхода    */
    double Value;                  /* +0x00 = 1111 (уровень 1)     */
    char   pad[0x08];              /* +0x08                        */
    Level* L1;                     /* +0x10 уровень 2              */
} Game;

static Game* g_game = NULL;        /* СТАТИЧЕСКИЙ ЯКОРЬ: target_game.exe+X */

_Static_assert(offsetof(Level, Value)  == 0x00, "Value offset");
_Static_assert(offsetof(Level, Next)   == 0x10, "Next offset");
_Static_assert(offsetof(Level, Marker) == 0x18, "Marker offset");
_Static_assert(offsetof(Game, Value)   == 0x00, "Game.Value offset");
_Static_assert(offsetof(Game, L1)      == 0x10, "Game.L1 offset");

static void* xmalloc(size_t n)
{
    void* p = malloc(n);
    if (p == NULL) { printf("[FATAL] out of memory\n"); exit(1); }
    return p;
}

static void noise_alloc(void)
{
    void* p = malloc((size_t)(rand() % 8192) + 1);
    if (p) free(p);
}

static void gc_rebuild(void)
{
    static const double markers[4] = { 9001.0, 9002.0, 9003.0, 9004.0 };
    Level* fresh[4];
    Level* old;
    double money;
    int i;

    /* при первом вызове цепочки ещё нет — денег 100.0 */
    money = 100.0;
    if (g_game->L1 != NULL) {
        Level* l3 = g_game->L1->Next->Next;
        if (l3 != NULL) money = l3->Value;
    }

    for (i = 0; i < 4; i++) {
        fresh[i] = (Level*)xmalloc(sizeof(Level));
        noise_alloc();
        memset(fresh[i], 0, sizeof(Level));
        fresh[i]->Value  = money;
        fresh[i]->Marker = markers[i];
        if (i > 0) fresh[i - 1]->Next = fresh[i];
    }
    fresh[0]->Value = 2222.0;                 /* уровень 2 */
    fresh[1]->Value = 3333.0;                 /* уровень 3 */
    /* уровень 4 (fresh[2]) и зеркало (fresh[3]) держат ДЕНЬГИ */

    old = g_game->L1;
    g_game->L1 = fresh[0];
    while (old != NULL) {
        Level* nx = old->Next;
        free(old);
        old = nx;
    }

    printf("[GC    ] L1=%p L2=%p L3=%p L4=%p  (деньги=%.1f)\n",
        (void*)fresh[0], (void*)fresh[1], (void*)fresh[2], (void*)fresh[3],
        fresh[2]->Value);
}

static void add_money(double amount)
{
    Level* l3 = g_game->L1->Next->Next;       /* уровень 4 — официальные деньги */
    l3->Value += amount;
    l3->Next->Value = l3->Value;              /* зеркало L4 */
    printf("[MONEY ] +%.0f -> %.1f  (L3=%p)\n", amount, l3->Value, (void*)l3);
}

static void print_chain(void)
{
    ULONG_PTR base = (ULONG_PTR)GetModuleHandleA(NULL);
    ULONG_PTR anchor = (ULONG_PTR)&g_game;
    Level* l1 = g_game->L1;
    Level* l2 = l1->Next;
    Level* l3 = l2->Next;
    Level* l4 = l3->Next;
    printf("=== GROUND TRUTH ===\n");
    printf("module base      = 0x%llX\n", (unsigned long long)base);
    printf("&g_game          = 0x%llX  (target_game.exe+0x%llX)\n",
        (unsigned long long)anchor, (unsigned long long)(anchor - base));
    printf("Game (1111)      = %p   Value@Game+0\n", (void*)g_game);
    printf("L1   (2222)      = %p   Value@L1+0, Next@L1+0x10\n", (void*)l1);
    printf("L2   (3333)      = %p\n", (void*)l2);
    printf("L3   (ДЕНЬГИ)    = %p   Value@L3+0\n", (void*)l3);
    printf("L4   (ДЕНЬГИ)    = %p\n", (void*)l4);
    printf("ручные записи (офсеты hex сверху вниз, все показывают СВОЁ число):\n");
    printf("  {0}                     -> 1111\n");
    printf("  {0, 0}                  -> 1111\n");
    printf("  {0, 10, 0}              -> 2222\n");
    printf("  {0, 10, 10, 0}          -> 3333\n");
    printf("  {0, 10, 10, 10, 0}      -> ДЕНЬГИ\n");
    printf("  {0, 10, 10, 10, 10, 0}  -> ДЕНЬГИ\n");
    printf("====================\n");
}

int main(int argc, char** argv)
{
    int money_ms = (argc > 1) ? atoi(argv[1]) : 2000;
    int gc_ms    = (argc > 2) ? atoi(argv[2]) : 15000;
    DWORD lastMoney, lastGC, now;

    setvbuf(stdout, NULL, _IONBF, 0);
    SetConsoleOutputCP(65001);       /* UTF-8 в консоли — без кракозябр */
    srand((unsigned)GetTickCount());
    SetConsoleTitleA("TargetGame v3 (AutoBase Finder test target)");

    g_game = (Game*)xmalloc(sizeof(Game));
    memset(g_game, 0, sizeof(*g_game));
    g_game->Value = 1111.0;

    gc_rebuild();

    printf("TargetGame v3 started. money every %d ms, GC every %d ms\n",
        money_ms, gc_ms);
    printf("Keys: [space] +100  [g] GC now  [p] print chain  [q] quit\n");
    print_chain();

    lastMoney = GetTickCount();
    lastGC = lastMoney;

    for (;;) {
        if (_kbhit()) {
            int c = _getch();
            if (c == 'q' || c == 'Q') break;
            if (c == ' ') add_money(100.0);
            else if (c == 'g' || c == 'G') { gc_rebuild(); lastGC = GetTickCount(); }
            else if (c == 'p' || c == 'P') print_chain();
        }
        now = GetTickCount();
        if (now - lastMoney >= (DWORD)money_ms) {
            add_money(10.0 + (double)(rand() % 40));
            lastMoney = now;
        }
        if (now - lastGC >= (DWORD)gc_ms) {
            gc_rebuild();
            lastGC = now;
        }
        Sleep(50);
    }

    printf("bye\n");
    return 0;
}
