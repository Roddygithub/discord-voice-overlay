use anyhow::Result;
use gdk4::prelude::*;
use gdk4::Display;
use gtk4::prelude::*;
use gtk4::Application;
use gtk4_layer_shell::{Layer, LayerShell as _};
use std::cell::RefCell;
use std::rc::Rc;

use crate::config::{Config, MonitorConfig};

/// Pointer pass-through: an empty input region makes the Wayland compositor
/// deliver all pointer input to surfaces below the overlay while it stays
/// fully rendered. Keyboard interactivity stays disabled independently.
pub fn empty_input_region() -> gtk4::cairo::Region {
    gtk4::cairo::Region::create()
}

pub fn apply_click_through(window: &gtk4::ApplicationWindow) {
    let Some(surface) = window.surface() else {
        return;
    };
    surface.set_input_region(Some(&empty_input_region()));
    tracing::debug!("Applied empty input region (pointer click-through)");
}

fn monitor_at_cursor(display: &Display) -> Option<gdk4::Monitor> {
    let seat = display.default_seat()?;
    let device = seat.pointer()?;
    let (surface, _, _) = device.surface_at_position();
    display.monitor_at_surface(&surface?)
}

fn resolve_monitor(monitor_config: &MonitorConfig) -> Option<gdk4::Monitor> {
    let display = Display::default()?;
    let monitors = display.monitors();
    let n = monitors.n_items();
    if n == 0 {
        return None;
    }

    let first = || monitors.item(0).and_downcast::<gdk4::Monitor>();

    match monitor_config {
        MonitorConfig::Primary => first(),
        MonitorConfig::Active | MonitorConfig::Cursor => monitor_at_cursor(&display).or_else(first),
        MonitorConfig::Index(idx) => {
            let idx = wrapped_monitor_index(*idx, n)?;
            monitors.item(idx).and_downcast::<gdk4::Monitor>()
        }
    }
}

pub fn create_layer_shell_window(
    app: &Application,
    config: &Config,
    current: &Rc<RefCell<Option<gdk4::Monitor>>>,
) -> Result<gtk4::ApplicationWindow> {
    let window = gtk4::ApplicationWindow::builder()
        .application(app)
        .title("Discord Voice Overlay")
        .decorated(false)
        .resizable(false)
        .build();

    window.init_layer_shell();
    window.set_layer(Layer::Overlay);
    window.set_keyboard_mode(gtk4_layer_shell::KeyboardMode::None);
    set_anchors(
        &window,
        &config.overlay.position,
        config.overlay.custom_x,
        config.overlay.custom_y,
    );
    window.set_exclusive_zone(0);

    if let Some(monitor) = resolve_monitor(&config.overlay.monitor) {
        window.set_monitor(Some(&monitor));
        *current.borrow_mut() = Some(monitor);
        tracing::debug!("Overlay assigned to monitor");
    }

    // GTK auto-sizes the window from the ScrolledWindow's natural content
    // height (propagate_natural_height). No fixed size: the background
    // panel wraps exactly the visible participant rows.
    window.add_css_class("vesktop-voice-overlay");

    // The GdkSurface only exists once the window is mapped; re-apply on every
    // map so remounts keep pointer pass-through.
    window.connect_map(apply_click_through);

    Ok(window)
}

pub fn update_position(
    window: &gtk4::ApplicationWindow,
    position: &str,
    custom_x: i32,
    custom_y: i32,
) {
    tracing::debug!(
        "update_position called: position={}, custom_x={}, custom_y={}",
        position,
        custom_x,
        custom_y
    );
    set_anchors(window, position, custom_x, custom_y);
}

pub fn update_monitor(
    window: &gtk4::ApplicationWindow,
    monitor_config: &MonitorConfig,
    current: &Rc<RefCell<Option<gdk4::Monitor>>>,
) {
    if let Some(monitor) = resolve_monitor(monitor_config) {
        if !monitor_target_changed(current.borrow().as_ref(), Some(&monitor)) {
            return;
        }
        window.set_monitor(Some(&monitor));
        *current.borrow_mut() = Some(monitor);
        tracing::debug!("Overlay moved to monitor");
    } else {
        // The topology may temporarily contain no outputs. Do not detach the
        // layer surface; forget the stale object so the next topology event
        // will reapply the newly resolved target.
        current.borrow_mut().take();
    }
}

fn monitor_target_changed<T: PartialEq>(current: Option<&T>, target: Option<&T>) -> bool {
    target.is_some_and(|target| current != Some(target))
}

fn wrapped_monitor_index(index: u32, count: u32) -> Option<u32> {
    (count > 0).then(|| index % count)
}

fn set_anchors(window: &gtk4::ApplicationWindow, position: &str, custom_x: i32, custom_y: i32) {
    use gtk4_layer_shell::{Edge, LayerShell as _};

    for edge in [Edge::Left, Edge::Right, Edge::Top, Edge::Bottom] {
        window.set_anchor(edge, false);
    }

    window.set_margin(Edge::Left, 0);
    window.set_margin(Edge::Right, 0);
    window.set_margin(Edge::Top, 0);
    window.set_margin(Edge::Bottom, 0);

    match position {
        "top-left" => {
            window.set_anchor(Edge::Top, true);
            window.set_anchor(Edge::Left, true);
            window.set_margin(Edge::Top, 20);
            window.set_margin(Edge::Left, 20);
        }
        "top-right" => {
            window.set_anchor(Edge::Top, true);
            window.set_anchor(Edge::Right, true);
            window.set_margin(Edge::Top, 20);
            window.set_margin(Edge::Right, 20);
        }
        "bottom-left" => {
            window.set_anchor(Edge::Bottom, true);
            window.set_anchor(Edge::Left, true);
            window.set_margin(Edge::Bottom, 20);
            window.set_margin(Edge::Left, 20);
        }
        "bottom-right" => {
            window.set_anchor(Edge::Bottom, true);
            window.set_anchor(Edge::Right, true);
            window.set_margin(Edge::Bottom, 20);
            window.set_margin(Edge::Right, 20);
        }
        "center" => {
            // With no anchors, layer-shell centers a natural-size surface.
        }
        "custom" => {
            window.set_anchor(Edge::Top, true);
            window.set_anchor(Edge::Left, true);
            window.set_margin(Edge::Top, custom_y);
            window.set_margin(Edge::Left, custom_x);
        }
        _ => {
            window.set_anchor(Edge::Top, true);
            window.set_anchor(Edge::Right, true);
            window.set_margin(Edge::Top, 20);
            window.set_margin(Edge::Right, 20);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_input_region_is_actually_empty() {
        let region = empty_input_region();
        assert!(region.is_empty());
        assert_eq!(region.num_rectangles(), 0);
    }

    #[test]
    fn monitor_target_changes_are_deduplicated_and_empty_topology_is_safe() {
        assert!(!monitor_target_changed(Some(&2), Some(&2)));
        assert!(monitor_target_changed(Some(&1), Some(&2)));
        assert!(!monitor_target_changed(None::<&u8>, None));
        assert_eq!(wrapped_monitor_index(0, 2), Some(0));
        assert_eq!(wrapped_monitor_index(2, 2), Some(0));
        assert_eq!(wrapped_monitor_index(5, 2), Some(1));
        assert_eq!(wrapped_monitor_index(3, 0), None);
    }
}
