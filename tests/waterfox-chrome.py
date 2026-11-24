#!/usr/bin/env python3
"""Check Textfox styles in a disposable Waterfox profile."""

from pathlib import Path
import time

from gecko_session import browser_argument, gecko_profile


ROOT = Path(__file__).resolve().parents[1]
PREFERENCES = {
    "browser.statusbar.enabled": True,
    "browser.tabs.verticalTabs.tree.enabled": True,
    "sidebar.revamp": True,
    "sidebar.verticalTabs": True,
    "sidebar.visibility": "always-show",
    "ui.prefersReducedMotion": 0,
}
DARK_THEME = {
    "id": "textfox-chrome-test@local",
    "accentcolor": "#151923",
    "textcolor": "#dee3ed",
}

THEME_COLORS = """
const root = document.documentElement;
Services.obs.notifyObservers(
  { wrappedJSObject: { theme: arguments[0] } },
  "lightweight-theme-styling-update"
);
const sample = document.createElementNS("http://www.w3.org/1999/xhtml", "span");
root.append(sample);
const color = (value) => {
  sample.style.setProperty("color", value, "important");
  return getComputedStyle(sample).color;
};
const colors = {
  border: getComputedStyle(document.querySelector("#nav-bar")).borderTopColor,
  accent: color("var(--tf-accent)"),
  fallbackBorder: color(
    "color-mix(in srgb, var(--tf-bg) 70%, var(--toolbarbutton-icon-fill, currentColor) 30%)"
  ),
  iconColor: color("var(--toolbarbutton-icon-fill)"),
};
sample.remove();
return colors;
"""

SIDEBAR = """
const controller = window.SidebarController;
const host = controller?.sidebarMain;
const wrapper = host?.shadowRoot?.querySelector(".buttons-wrapper");
const actions = wrapper?.querySelector(".tools-and-extensions:not(.overflow-button)");
const container = document.getElementById("sidebar-container");
if (!actions || !container) return null;
if (arguments[0]) {
  // Capture the animated frame even if it falls between two driver requests.
  container.removeAttribute("data-textfox-observed-shrink");
  const observer = new MutationObserver(() => {
    if (!container.hasAttribute("sidebar-ongoing-animations")) return;
    container.setAttribute("data-textfox-observed-shrink", getComputedStyle(container).flexShrink);
    observer.disconnect();
  });
  observer.observe(container, { attributes: true, attributeFilter: ["sidebar-ongoing-animations"] });
  controller.handleToolbarButtonClick();
}
const treeButton = document.querySelector(
  "#vertical-tabs[tree-tabs-enabled] #waterfox-tree-newtab-action-button"
);
const title = getComputedStyle(wrapper, "::before");
return {
  expanded: host.expanded,
  background: getComputedStyle(host).backgroundColor,
  orientation: actions.getAttribute("orientation"),
  arrangement: getComputedStyle(actions).justifyContent,
  title: title.content,
  titleTop: title.marginTop,
  ongoing: container.hasAttribute("sidebar-ongoing-animations"),
  observedShrink: container.getAttribute("data-textfox-observed-shrink"),
  treeButton: treeButton && {
    display: getComputedStyle(treeButton).display,
    rounding: getComputedStyle(treeButton).borderRadius,
  },
};
"""

STATUS = """
const root = document.documentElement;
const bar = document.getElementById("status-bar");
const label = document.querySelector("#status-text > #statuspanel-label");
const tab = document.querySelector(".tabbrowser-tab[fadein]:not([pinned]) > .tab-stack");
if (!bar || !label || !tab) return null;
return {
  fullscreen: root.getAttribute("inFullscreen") === "true",
  barTitleDisplay: getComputedStyle(bar, "::before").display,
  barBorder: getComputedStyle(bar).borderTopWidth,
  barMargin: getComputedStyle(bar).marginTop,
  labelTransition: getComputedStyle(label).transitionDuration,
  tabAnimation: getComputedStyle(tab).animationName,
  reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,
};
"""


def wait_for(read, condition, description):
    deadline = time.monotonic() + 5
    while True:
        result = read()
        if result is not None and condition(result):
            return result
        if time.monotonic() >= deadline:
            raise AssertionError(f"{description}: {result}")
        time.sleep(0.05)


def check_colors(execute):
    execute("document.documentElement.style.setProperty('--tf-border-transition', '0s');")
    cases = [
        ("default", None, None, None),
        ("no custom colors", {}, None, None),
        ("explicit border", {"toolbar_field_border": "#365a87"}, "rgb(54, 90, 135)", None),
        ("explicit accent", {"tab_line": "#ed774a"}, None, "rgb(237, 119, 74)"),
        ("both colors", {"toolbar_field_border": "#365a87", "tab_line": "#ed774a"},
         "rgb(54, 90, 135)", "rgb(237, 119, 74)"),
        ("transparent border", {"toolbar_field_border": "transparent"}, None, None),
        ("light theme fallback", {"accentcolor": "#eff4fb", "textcolor": "#374260"}, None, None),
        ("translucent border", {"toolbar_field_border": "#365a8780"},
         "rgba(54, 90, 135, 0.5)", None),
        ("return to dark fallback", {}, None, None),
    ]
    for name, colors, border, accent in cases:
        theme = None if colors is None else {**DARK_THEME, **colors}
        result = execute(THEME_COLORS, theme)
        assert result["border"] == (border or result["fallbackBorder"]), (name, result)
        assert result["accent"] == (accent or result["iconColor"]), (name, result)
    print(f"PASS {len(cases)} toolbar border and accent combinations")


def check_sidebar(execute):
    execute(THEME_COLORS, DARK_THEME)
    execute("document.documentElement.style.setProperty('--tf-rounding', '7px');")
    before = wait_for(lambda: execute(SIDEBAR), lambda _: True, "sidebar not ready")
    if not before["expanded"]:
        execute(SIDEBAR, True)
    expanded = wait_for(
        lambda: execute(SIDEBAR),
        lambda item: item["expanded"] and item["orientation"] == "horizontal" and not item["ongoing"],
        "sidebar did not expand",
    )
    assert expanded["background"] == "rgb(21, 25, 35)", expanded
    assert expanded["arrangement"] == "space-evenly" and expanded["title"] == '"tools"', expanded
    assert expanded["treeButton"] == {"display": "flex", "rounding": "7px"}, expanded

    execute(SIDEBAR, True)
    collapsed = wait_for(
        lambda: execute(SIDEBAR),
        lambda item: not item["expanded"] and item["orientation"] == "vertical" and not item["ongoing"],
        "sidebar did not collapse",
    )
    assert collapsed["observedShrink"] == "0", collapsed
    assert collapsed["background"] == expanded["background"], collapsed
    assert collapsed["titleTop"] == "-10px", collapsed
    print("PASS sidebar layout and tree-tab control")


def check_status_and_motion(execute):
    start = wait_for(lambda: execute(STATUS), lambda _: True, "status bar or tabs not ready")
    assert start["barBorder"] == "2px" and start["barMargin"] == "6px", start
    assert start["tabAnimation"] == "tf-tab-in" and start["labelTransition"] == "0.15s", start

    execute("Services.prefs.setIntPref('ui.prefersReducedMotion', 1);")
    wait_for(
        lambda: execute(STATUS),
        lambda item: item["reduced"] and item["tabAnimation"] == "none" and item["labelTransition"] == "0s",
        "reduced-motion styles did not take effect",
    )
    print("PASS reduced-motion preference disables the tab and status animations")

    execute("window.fullScreen = true;")
    full = wait_for(lambda: execute(STATUS), lambda item: item["fullscreen"], "fullscreen")
    assert full["barBorder"] == "0px" and full["barMargin"] == "0px", full
    assert full["barTitleDisplay"] == "none", full
    print("PASS fullscreen removes the status bar frame and title")


def main():
    browser = browser_argument(__doc__)
    tab_height = "return gBrowser.selectedTab.getBoundingClientRect().height;"
    with gecko_profile(browser, theme_dir=ROOT) as (_, _, execute):
        assert not execute("return Services.prefs.getBoolPref('sidebar.verticalTabs', false);")
        assert execute(tab_height) > 0, "Selected horizontal tab is invisible in a fresh profile"
        execute("document.documentElement.style.setProperty('--tf-display-horizontal-tabs', 'none');")
        assert execute(tab_height) == 0, "Explicit horizontal tab override was ignored"
        print("PASS fresh profile shows horizontal tabs and respects explicit hiding")
    with gecko_profile(browser, preferences=PREFERENCES, theme_dir=ROOT) as (_, _, execute):
        info = execute("return [Services.appinfo.name, Services.appinfo.version];")
        if info[0].lower() != "waterfox":
            raise RuntimeError(f"This test requires Waterfox, received {info[0]}.")
        print(f"Waterfox {info[1]}")
        assert execute(tab_height) > 0, "Selected vertical tab is invisible"
        assert execute("return document.getElementById('TabsToolbar').getBoundingClientRect().height;") == 0
        check_colors(execute)
        check_sidebar(execute)
        check_status_and_motion(execute)


if __name__ == "__main__":
    main()
