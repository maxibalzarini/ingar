'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');

class AppDatabase {
  constructor(userDataPath) {
    this.dataDir = path.join(userDataPath, 'data');
    this.backupDir = path.join(userDataPath, 'backups');
    fs.mkdirSync(this.dataDir, { recursive: true });
    fs.mkdirSync(this.backupDir, { recursive: true });

    this.filePath = path.join(this.dataDir, 'ingar_can_analyzer.sqlite');
    this.db = new DatabaseSync(this.filePath);
    this.db.exec(`
      PRAGMA journal_mode = WAL;
      PRAGMA foreign_keys = ON;
      PRAGMA synchronous = NORMAL;

      CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      ) STRICT;

      CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      ) STRICT;

      CREATE TABLE IF NOT EXISTS app_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_utc TEXT NOT NULL,
        ended_utc TEXT,
        clean_shutdown INTEGER NOT NULL DEFAULT 0 CHECK(clean_shutdown IN (0, 1)),
        app_version TEXT NOT NULL
      ) STRICT;
    `);

    this.upsertMeta('schema_version', '1');
  }

  upsertMeta(key, value) {
    this.db.prepare(`
      INSERT INTO app_meta(key, value, updated_utc)
      VALUES (?, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(key) DO UPDATE SET
        value = excluded.value,
        updated_utc = CURRENT_TIMESTAMP
    `).run(key, String(value));
  }

  getMeta(key, fallback = null) {
    const row = this.db.prepare('SELECT value FROM app_meta WHERE key = ?').get(key);
    return row ? row.value : fallback;
  }

  getSettings() {
    const defaults = {
      startMaximized: true,
      restoreWindow: true,
      keepTechnicalLogs: true,
      language: 'es-AR',
      lastView: 'inicio'
    };

    const row = this.db.prepare('SELECT value_json FROM settings WHERE key = ?').get('main');
    if (!row) {
      this.saveSettings(defaults);
      return defaults;
    }

    try {
      return { ...defaults, ...JSON.parse(row.value_json) };
    } catch {
      this.saveSettings(defaults);
      return defaults;
    }
  }

  saveSettings(settings) {
    const safe = {
      startMaximized: Boolean(settings.startMaximized),
      restoreWindow: Boolean(settings.restoreWindow),
      keepTechnicalLogs: Boolean(settings.keepTechnicalLogs),
      language: settings.language === 'es-ES' ? 'es-ES' : 'es-AR',
      lastView: typeof settings.lastView === 'string' ? settings.lastView : 'inicio'
    };

    this.db.prepare(`
      INSERT INTO settings(key, value_json, updated_utc)
      VALUES ('main', ?, CURRENT_TIMESTAMP)
      ON CONFLICT(key) DO UPDATE SET
        value_json = excluded.value_json,
        updated_utc = CURRENT_TIMESTAMP
    `).run(JSON.stringify(safe));

    return safe;
  }

  getWindowState() {
    const row = this.db.prepare('SELECT value_json FROM settings WHERE key = ?').get('window');
    if (!row) return null;

    try {
      const state = JSON.parse(row.value_json);
      if (
        Number.isFinite(state.x) &&
        Number.isFinite(state.y) &&
        Number.isFinite(state.width) &&
        Number.isFinite(state.height)
      ) {
        return state;
      }
    } catch {}
    return null;
  }

  saveWindowState(state) {
    const safe = {
      x: Math.trunc(state.x),
      y: Math.trunc(state.y),
      width: Math.max(1000, Math.trunc(state.width)),
      height: Math.max(650, Math.trunc(state.height)),
      maximized: Boolean(state.maximized)
    };

    this.db.prepare(`
      INSERT INTO settings(key, value_json, updated_utc)
      VALUES ('window', ?, CURRENT_TIMESTAMP)
      ON CONFLICT(key) DO UPDATE SET
        value_json = excluded.value_json,
        updated_utc = CURRENT_TIMESTAMP
    `).run(JSON.stringify(safe));
  }

  startRun(appVersion) {
    const previous = this.db.prepare(`
      SELECT id, started_utc
      FROM app_runs
      WHERE clean_shutdown = 0
      ORDER BY id DESC
      LIMIT 1
    `).get();

    const result = this.db.prepare(`
      INSERT INTO app_runs(started_utc, app_version)
      VALUES (CURRENT_TIMESTAMP, ?)
    `).run(appVersion);

    return {
      runId: Number(result.lastInsertRowid),
      recoveredFromUnexpectedShutdown: Boolean(previous),
      previousStartedUtc: previous?.started_utc ?? null
    };
  }

  finishRun(runId) {
    this.db.prepare(`
      UPDATE app_runs
      SET ended_utc = CURRENT_TIMESTAMP,
          clean_shutdown = 1
      WHERE id = ?
    `).run(runId);
  }

  getDatabaseHealth() {
    const integrity = this.db.prepare('PRAGMA quick_check').get();
    return {
      ok: integrity?.quick_check === 'ok',
      result: integrity?.quick_check ?? 'unknown',
      filePath: this.filePath,
      sizeBytes: fs.existsSync(this.filePath) ? fs.statSync(this.filePath).size : 0
    };
  }

  close() {
    this.db.close();
  }
}

module.exports = { AppDatabase };
