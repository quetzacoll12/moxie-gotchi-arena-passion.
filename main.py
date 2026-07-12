from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import random
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COOLDOWN_MS = 300000 # 5 minutos de descanso entre partidos

def init_db():
    conn = sqlite3.connect("moxie.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS moxie_profile (
            id INTEGER PRIMARY KEY,
            name TEXT,
            level INTEGER,
            exp INTEGER,
            coins INTEGER,
            hp INTEGER,
            max_hp INTEGER,
            mp INTEGER,
            max_mp INTEGER,
            atk INTEGER,
            skill_points INTEGER,
            skill_fire TEXT,
            skill_def TEXT,
            skill_speed TEXT,
            last_rest_timestamp INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            event_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("SELECT COUNT(*) FROM moxie_profile")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO moxie_profile 
            (id, name, level, exp, coins, hp, max_hp, mp, max_mp, atk, skill_points, skill_fire, skill_def, skill_speed, last_rest_timestamp) 
            VALUES (1, 'Goleador Ferviente (Pasión)', 1, 0, 150, 100, 100, 50, 50, 15, 0, 'No Desbloqueado', 'No Desbloqueado', 'No Desbloqueado', 0)
        """)
        cursor.execute("INSERT INTO game_logs (category, event_text) VALUES ('PASIÓN', 'Estadio inicializado. ¡Que viva el fútbol!')")
    conn.commit()
    conn.close()

init_db()

class ActionRequest(BaseModel):
    action_type: str

class SkillRequest(BaseModel):
    branch: str
    skill_name: str

class BattleRequest(BaseModel):
    attack_type: str

class SelectMoxieRequest(BaseModel):
    moxie_name: str

class SyncHPRequest(BaseModel):
    current_hp: int

@app.post("/api/select-initial")
async def select_initial(request: SelectMoxieRequest):
    conn = sqlite3.connect("moxie.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE moxie_profile 
        SET name = ?, level = 1, exp = 0, hp = 100, max_hp = 100, mp = 50, max_mp = 50, atk = 15, skill_points = 0,
            skill_fire = 'No Desbloqueado', skill_def = 'No Desbloqueado', skill_speed = 'No Desbloqueado', last_rest_timestamp = 0
        WHERE id = 1
    """, (request.moxie_name,))
    
    log_msg = f"¡Hinchada/Estilo cambiado a {request.moxie_name}! La pasión se renueva."
    cursor.execute("INSERT INTO game_logs (category, event_text) VALUES ('PASIÓN', ?)", (log_msg,))
    conn.commit()
    conn.close()
    return {"message": log_msg}

@app.get("/api/game-state")
async def get_game_state(filter_type: str = "TODOS"):
    conn = sqlite3.connect("moxie.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, level, exp, coins, hp, max_hp, mp, max_mp, atk, skill_points, skill_fire, skill_def, skill_speed, last_rest_timestamp 
        FROM moxie_profile WHERE id = 1
    """)
    p = cursor.fetchone()
    
    if filter_type == "TODOS":
        cursor.execute("SELECT event_text FROM game_logs ORDER BY id DESC LIMIT 5")
    else:
        cursor.execute("SELECT event_text FROM game_logs WHERE category = ? ORDER BY id DESC LIMIT 5", (filter_type,))
        
    logs = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    now_ms = int(time.time() * 1000)
    time_passed = now_ms - p[13]
    remaining_cd = max(0, COOLDOWN_MS - time_passed)
    
    return {
        "moxie": {
            "name": p[0], "level": p[1], "exp": p[2], "coins": p[3], "hp": p[4], "max_hp": p[5],
            "mp": p[6], "max_mp": p[7], "atk": p[8], "sp": p[9], "skill_fire": p[10], "skill_def": p[11], "skill_speed": p[12]
        },
        "enemy": { "max_hp": p[1] * 120 },
        "remaining_cooldown_ms": remaining_cd,
        "logs": logs
    }

@app.post("/api/moxie-action")
async def moxie_action(request: ActionRequest):
    conn = sqlite3.connect("moxie.db")
    cursor = conn.cursor()
    cursor.execute("SELECT coins FROM moxie_profile WHERE id = 1")
    coins = cursor.fetchone()[0]
    
    msg = ""
    success = True
    
    if request.action_type == "feed":
        if coins >= 20:
            cursor.execute("UPDATE moxie_profile SET max_hp = max_hp + 10, hp = hp + 10, coins = coins - 20 WHERE id = 1")
            msg = "🎟️ ¡Entrada Comprada! Apoyo masivo al club: +10 Resistencia. Costo: 20 MC."
        else:
            success = False
            msg = "❌ Monedas insuficientes para la entrada (20 MC)."
            
    elif request.action_type == "train":
        if coins >= 50:
            cursor.execute("UPDATE moxie_profile SET atk = atk + 3, skill_points = skill_points + 1, exp = exp + 15, coins = coins - 50 WHERE id = 1")
            msg = "⚽ ¡Entrenamiento Táctico Intenso! +3 Ofensiva, +1 SP, +15 EXP de Equipo. Costo: 50 MC."
        else:
            success = False
            msg = "❌ Monedas insuficientes para entrenar (50 MC)."

    if success:
        cursor.execute("SELECT exp, level FROM moxie_profile WHERE id = 1")
        curr_exp, curr_lvl = cursor.fetchone()
        target_lvl = 1 + (curr_exp // 100)
        if target_lvl > curr_lvl:
            cursor.execute("UPDATE moxie_profile SET level = ?, skill_points = skill_points + 1 WHERE id = 1", (target_lvl,))
            msg += f" 🏆 ¡ASCENSO DE DIVISIÓN! Ahora estás en Nivel {target_lvl}."
        
        cursor.execute("INSERT INTO game_logs (category, event_text) VALUES ('CLUB', ?)", (msg,))
        conn.commit()
    
    conn.close()
    return {"success": success, "message": msg}

@app.post("/api/secure-rest")
async def secure_rest():
    conn = sqlite3.connect("moxie.db")
    cursor = conn.cursor()
    cursor.execute("SELECT hp, max_hp, max_mp, last_rest_timestamp FROM moxie_profile WHERE id = 1")
    chp, mhp, mmp, last_rest = cursor.fetchone()
    
    now_ms = int(time.time() * 1000)
    if now_ms - last_rest < COOLDOWN_MS:
        conn.close()
        raise HTTPException(status_code=400, detail="Cooldown activo. Los jugadores están en el vestuario.")
        
    heal_amount = int(mhp * 0.30)
    new_hp = min(mhp, chp + heal_amount)
    
    cursor.execute("""
        UPDATE moxie_profile 
        SET hp = ?, mp = ?, last_rest_timestamp = ? 
        WHERE id = 1
    """, (new_hp, mmp, now_ms))
    
    log_msg = f"⏱️ Tiempo de Entretiempo: Recuperación del 30% de Energía y Táctica restaurada."
    cursor.execute("INSERT INTO game_logs (category, event_text) VALUES ('CLUB', ?)", (log_msg,))
    conn.commit()
    conn.close()
    
    return {"success": True, "healed": heal_amount, "new_hp": new_hp, "new_mp": mmp, "cooldown_ms": COOLDOWN_MS}

@app.post("/api/sync-battle-damage")
async def sync_battle_damage(request: SyncHPRequest):
    conn = sqlite3.connect("moxie.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE moxie_profile SET hp = ? WHERE id = 1", (request.current_hp,))
    conn.commit()
    conn.close()
    return {"success": True}

@app.post("/api/unlock-skill")
async def unlock_skill(request: SkillRequest):
    conn = sqlite3.connect("moxie.db")
    cursor = conn.cursor()
    cursor.execute("SELECT skill_points FROM moxie_profile WHERE id = 1")
    sp = cursor.fetchone()[0]
    
    if sp < 1:
        conn.close()
        return {"success": False, "message": "Faltan Puntos Estratégicos (SP)."}
        
    if request.branch == "fire":
        cursor.execute("UPDATE moxie_profile SET skill_fire = ?, skill_points = skill_points - 1 WHERE id = 1", (request.skill_name,))
    elif request.branch == "def":
        cursor.execute("UPDATE moxie_profile SET skill_def = ?, max_hp = max_hp + 40, hp = hp + 40, skill_points = skill_points - 1 WHERE id = 1", (request.skill_name,))
    elif request.branch == "speed":
        cursor.execute("UPDATE moxie_profile SET skill_speed = ?, skill_points = skill_points - 1 WHERE id = 1", (request.skill_name,))
        
    log_msg = f"⚽ Pizarra Táctica Actualizada: Aprendiste '{request.skill_name}'"
    cursor.execute("INSERT INTO game_logs (category, event_text) VALUES ('ESTRATEGIA', ?)", (log_msg,))
    conn.commit()
    conn.close()
    return {"success": True, "message": f"¡{request.skill_name} activada!"}

@app.post("/api/execute-attack")
async def execute_attack(request: BattleRequest):
    conn = sqlite3.connect("moxie.db")
    cursor = conn.cursor()
    cursor.execute("SELECT atk, level, mp FROM moxie_profile WHERE id = 1")
    base_atk, level, current_mp = cursor.fetchone()
    
    damage = random.randint(10, 18) + (base_atk // 2)
    flavor_text = ""
    mana_cost = 0
    
    if request.attack_type != "tackle":
        mana_cost = 15
        if current_mp < mana_cost:
            conn.close()
            return {"error": True, "message": "❌ ¡Sin barra de Táctica (MP) suficiente!"}

    if request.attack_type == "tackle":
        flavor_text = f"👟 ¡Pase filtrado y remate! Generas {damage} puntos de presión."
    elif request.attack_type == "fire":
        damage += 30
        flavor_text = f"🔥 ¡TIRO LIBRE AL ÁNGULO! Brutal despliegue de pasión: {damage} puntos."
    elif request.attack_type == "def":
        damage = 6
        flavor_text = f"🛡️ Táctica 'Catenaccio' (Defensa Total). Reduces daño y sumas {damage} puntos."
    elif request.attack_type == "speed":
        damage = int(damage * 1.9)
        flavor_text = f"⚡ ¡Contraataque Explosivo por la banda! {damage} puntos letales."
        
    enemy_counter = random.randint(5, 12) + (level * 3)
    new_mp = current_mp - mana_cost
    
    cursor.execute("UPDATE moxie_profile SET mp = ? WHERE id = 1", (new_mp,))
    cursor.execute("INSERT INTO game_logs (category, event_text) VALUES ('PARTIDO', ?)", (flavor_text,))
    conn.commit()
    conn.close()
    
    return {
        "error": False, "player_dmg": damage, "enemy_dmg": enemy_counter, "flavor": flavor_text, "mana_used": mana_cost
    }

@app.post("/api/victory-reward")
async def victory_reward():
    conn = sqlite3.connect("moxie.db")
    cursor = conn.cursor()
    cursor.execute("SELECT level FROM moxie_profile WHERE id = 1")
    level = cursor.fetchone()[0]
    
    exp_gain = 25 + (level * 10)
    coin_gain = 40 + (level * 15)
    
    roll = random.random()
    dropped_item = "Ninguno"
    if roll < 0.25: dropped_item = "Bebida Isotónica"
    elif roll >= 0.25 and roll < 0.50: dropped_item = "Gel de Resistencia"
        
    cursor.execute("UPDATE moxie_profile SET exp = exp + ?, coins = coins + ? WHERE id = 1", (exp_gain, coin_gain))
    
    cursor.execute("SELECT exp, level FROM moxie_profile WHERE id = 1")
    curr_exp, curr_lvl = cursor.fetchone()
    target_lvl = 1 + (curr_exp // 100)
    
    msg = f"🎉 ¡VICTORIA EN EL DERBI! Sumas +{exp_gain} EXP y +{coin_gain} MC de patrocinadores."
    if dropped_item != "Ninguno": msg += f" ¡La hinchada te obsequia: {dropped_item}!"
        
    if target_lvl > curr_lvl:
        cursor.execute("UPDATE moxie_profile SET level = ?, skill_points = skill_points + 1 WHERE id = 1", (target_lvl,))
        msg += f" 🏆 ¡ASCENSO DE CATEGORÍA!"
        
    cursor.execute("INSERT INTO game_logs (category, event_text) VALUES ('PARTIDO', ?)", (msg,))
    conn.commit()
    conn.close()
    return {"message": msg, "dropped": dropped_item}