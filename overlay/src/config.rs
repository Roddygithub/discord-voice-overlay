use anyhow::Result;
use dirs::config_dir;
use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use std::str::FromStr;
use tracing::debug;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Config {
    #[serde(default)]
    pub overlay: OverlayConfig,
    #[serde(default)]
    pub socket: SocketConfig,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum UserDisplayMode {
    Always,
    #[default]
    SpeakingOnly,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum NameDisplayMode {
    Always,
    #[default]
    SpeakingOnly,
    Never,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum AvatarSizeMode {
    #[default]
    Small,
    Large,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum MonitorConfig {
    #[default]
    Primary,
    Active,
    Cursor,
    Index(u32),
}

impl MonitorConfig {
    pub fn from_str(s: &str) -> Option<Self> {
        Self::try_from(s).ok()
    }

    pub fn tracks_cursor(&self) -> bool {
        matches!(self, Self::Active | Self::Cursor)
    }
}

impl TryFrom<&str> for MonitorConfig {
    type Error = ();

    fn try_from(s: &str) -> Result<Self, Self::Error> {
        match s {
            "" | "primary" => Ok(Self::Primary),
            "active" => Ok(Self::Active),
            "cursor" => Ok(Self::Cursor),
            _ => s
                .strip_prefix("index:")
                .and_then(|index| index.parse::<u32>().ok())
                .map(Self::Index)
                .ok_or(()),
        }
    }
}

impl FromStr for MonitorConfig {
    type Err = ();

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        Self::try_from(s)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OverlayConfig {
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default = "default_position")]
    pub position: String,
    #[serde(default)]
    pub custom_x: i32,
    #[serde(default)]
    pub custom_y: i32,
    #[serde(default = "default_max_participants")]
    pub max_participants: usize,
    #[serde(default)]
    pub user_display: UserDisplayMode,
    #[serde(default)]
    pub name_display: NameDisplayMode,
    #[serde(default)]
    pub avatar_size_mode: AvatarSizeMode,
    #[serde(default)]
    pub monitor: MonitorConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OverlaySettings {
    pub enabled: bool,
    pub position: String,
    pub custom_x: i32,
    pub custom_y: i32,
    pub user_display: UserDisplayMode,
    pub name_display: NameDisplayMode,
    pub avatar_size_mode: AvatarSizeMode,
    #[serde(default)]
    pub monitor: String,
}

impl OverlaySettings {
    pub fn is_valid(&self) -> bool {
        matches!(
            self.position.as_str(),
            "top-left" | "top-right" | "bottom-left" | "bottom-right" | "center" | "custom"
        ) && (-32_768..=32_768).contains(&self.custom_x)
            && (-32_768..=32_768).contains(&self.custom_y)
            && MonitorConfig::from_str(&self.monitor).is_some()
    }
}

impl Default for OverlayConfig {
    fn default() -> Self {
        Self {
            enabled: default_true(),
            position: default_position(),
            custom_x: 0,
            custom_y: 0,
            max_participants: default_max_participants(),
            user_display: UserDisplayMode::default(),
            name_display: NameDisplayMode::default(),
            avatar_size_mode: AvatarSizeMode::default(),
            monitor: MonitorConfig::default(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SocketConfig {
    #[serde(default = "default_socket_path")]
    pub path: String,
}

impl Default for SocketConfig {
    fn default() -> Self {
        Self {
            path: default_socket_path(),
        }
    }
}

fn default_position() -> String {
    "top-right".into()
}
fn default_max_participants() -> usize {
    10
}
fn default_true() -> bool {
    true
}
fn default_socket_path() -> String {
    std::env::var("XDG_RUNTIME_DIR")
        .map(|dir| format!("{}/vesktop-voice-overlay.sock", dir))
        .unwrap_or_default()
}

static CONFIG_PATH: Lazy<PathBuf> = Lazy::new(|| {
    config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("vesktop-voice-overlay")
        .join("config.toml")
});

impl Config {
    /// Loads the optional TOML config file. The file is never written by the
    /// overlay: runtime settings arrive from the Vencord plugin over the
    /// socket and are applied in memory only.
    pub fn load() -> Result<Self> {
        let content = fs::read_to_string(&*CONFIG_PATH)?;
        let config: Config = toml::from_str(&content)?;
        debug!("Loaded config from {:?}", CONFIG_PATH);
        Ok(config)
    }

    pub fn socket_path(&self) -> Result<&str> {
        if self.socket.path.is_empty() {
            anyhow::bail!("XDG_RUNTIME_DIR is required unless socket.path is configured");
        }
        Ok(&self.socket.path)
    }

    pub fn apply_overlay_settings(&mut self, settings: OverlaySettings) {
        self.overlay.enabled = settings.enabled;
        self.overlay.position = settings.position;
        self.overlay.custom_x = settings.custom_x;
        self.overlay.custom_y = settings.custom_y;
        self.overlay.user_display = settings.user_display;
        self.overlay.name_display = settings.name_display;
        self.overlay.avatar_size_mode = settings.avatar_size_mode;
        if let Some(monitor) = MonitorConfig::from_str(&settings.monitor) {
            self.overlay.monitor = monitor;
        }
    }

    pub fn avatar_size_px(&self) -> i32 {
        match self.overlay.avatar_size_mode {
            AvatarSizeMode::Small => 28,
            AvatarSizeMode::Large => 40,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn avatar_size_mode_resolves_to_distinct_pixel_sizes() {
        let mut config = Config::default();
        assert_eq!(config.avatar_size_px(), 28);

        config.overlay.avatar_size_mode = AvatarSizeMode::Large;
        assert_eq!(config.avatar_size_px(), 40);

        config.overlay.avatar_size_mode = AvatarSizeMode::Small;
        assert_eq!(config.avatar_size_px(), 28);
    }

    #[test]
    fn apply_overlay_settings_carries_avatar_size_mode() {
        let mut config = Config::default();
        let settings = OverlaySettings {
            enabled: true,
            position: "custom".into(),
            custom_x: 800,
            custom_y: 300,
            user_display: UserDisplayMode::Always,
            name_display: NameDisplayMode::Always,
            avatar_size_mode: AvatarSizeMode::Large,
            monitor: "cursor".into(),
        };

        config.apply_overlay_settings(settings);

        assert_eq!(config.overlay.position, "custom");
        assert_eq!(config.overlay.custom_x, 800);
        assert_eq!(config.overlay.custom_y, 300);
        assert_eq!(config.overlay.avatar_size_mode, AvatarSizeMode::Large);
        assert_eq!(config.avatar_size_px(), 40);
        assert_eq!(config.overlay.monitor, MonitorConfig::Cursor);
    }

    #[test]
    fn missing_runtime_directory_fails_closed() {
        let mut config = Config::default();
        config.socket.path.clear();
        assert!(config.socket_path().is_err());
    }

    #[test]
    fn legacy_appearance_and_numeric_avatar_fields_remain_compatible() {
        let config: Config = toml::from_str(
            r#"
                [overlay]
                max_participants = 7
                avatar_size = 40

                [appearance]
                theme = "dark"
                speaking_pulse_ms = 500
                show_names = false
            "#,
        )
        .expect("legacy keys remain accepted");

        assert_eq!(config.overlay.max_participants, 7);
        assert_eq!(config.overlay.avatar_size_mode, AvatarSizeMode::Small);
    }

    #[test]
    fn monitor_config_parsing() {
        assert_eq!(MonitorConfig::from_str(""), Some(MonitorConfig::Primary));
        assert_eq!(
            MonitorConfig::from_str("primary"),
            Some(MonitorConfig::Primary)
        );
        assert_eq!(
            MonitorConfig::from_str("active"),
            Some(MonitorConfig::Active)
        );
        assert_eq!(
            MonitorConfig::from_str("cursor"),
            Some(MonitorConfig::Cursor)
        );
        assert_eq!(
            MonitorConfig::from_str("index:0"),
            Some(MonitorConfig::Index(0))
        );
        assert_eq!(
            MonitorConfig::from_str("index:2"),
            Some(MonitorConfig::Index(2))
        );
        for malformed in [
            "index:",
            "index:foo",
            "index:-1",
            "unknown",
            "index:4294967296",
        ] {
            assert_eq!(MonitorConfig::from_str(malformed), None);
        }
    }

    #[test]
    fn live_settings_replace_startup_monitor_as_the_runtime_value() {
        let mut runtime = Config::default(); // startup Primary
        let cursor = OverlaySettings {
            enabled: true,
            position: "top-right".into(),
            custom_x: 0,
            custom_y: 0,
            user_display: UserDisplayMode::default(),
            name_display: NameDisplayMode::default(),
            avatar_size_mode: AvatarSizeMode::default(),
            monitor: "cursor".into(),
        };
        runtime.apply_overlay_settings(cursor);
        assert_eq!(runtime.overlay.monitor, MonitorConfig::Cursor);

        let fixed = OverlaySettings {
            monitor: "index:2".into(),
            ..OverlaySettings {
                enabled: true,
                position: "top-right".into(),
                custom_x: 0,
                custom_y: 0,
                user_display: UserDisplayMode::default(),
                name_display: NameDisplayMode::default(),
                avatar_size_mode: AvatarSizeMode::default(),
                monitor: String::new(),
            }
        };
        runtime.apply_overlay_settings(fixed);
        assert_eq!(runtime.overlay.monitor, MonitorConfig::Index(2));
        // This is the state consumed by the runtime after applying the message;
        // it is not re-read from the immutable startup Config.
        assert_ne!(runtime.overlay.monitor, Config::default().overlay.monitor);
    }

    #[test]
    fn cursor_tracking_mode_transitions_are_idempotent() {
        let mut tracking = false;
        for mode in [MonitorConfig::Primary, MonitorConfig::Index(2)] {
            let wanted = mode.tracks_cursor();
            if wanted != tracking {
                tracking = wanted;
            }
            assert!(!tracking);
        }
        assert!(MonitorConfig::Cursor.tracks_cursor());
        tracking = MonitorConfig::Cursor.tracks_cursor();
        assert!(tracking);
        assert!(MonitorConfig::Cursor.tracks_cursor()); // repeated setting stays one tracker
        tracking = MonitorConfig::Index(2).tracks_cursor();
        assert!(!tracking);
    }
}
