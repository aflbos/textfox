(() => {
  "use strict";

  const browser = window.gBrowser;
  const menu = document.getElementById("moveTabOptionsMenu");
  const firstNativeItem = document.getElementById("context_moveToStart");
  if (!browser || !menu || !firstNativeItem || document.getElementById("textfox-move-tab-back")) {
    return;
  }

  const tabs = browser.tabContainer;
  tabs.setAttribute("textfox-tree-disclosure", "");
  const { ShortcutUtils } = ChromeUtils.importESModule("resource://gre/modules/ShortcutUtils.sys.mjs");
  const portuguese = /^pt(?:-|$)/i.test(Services.locale.appLocaleAsBCP47);
  const labels = portuguese
    ? {
        vertical: ["Mover uma posição para cima", "Mover uma posição para baixo"],
        ordered: ["Mover uma posição para trás", "Mover uma posição para frente"],
      }
    : {
        vertical: ["Move One Position Up", "Move One Position Down"],
        ordered: ["Move One Position Back", "Move One Position Forward"],
      };

  // Waterfox's disclosure button only handles input with the sidebar expanded.
  function handleCollapsedDisclosure(event) {
    if (event.button !== 0 || tabs.hasAttribute("expanded") ||
        !window.TreeTabsDnD?._isEnabled?.(tabs)) return;
    const button = event.target?.closest(".tab-tree-disclosure:not([hidden])");
    const tab = button?.closest(".tabbrowser-tab[data-tree-has-children]");
    if (!tab || tab.closing || tab.pinned) return;

    event.preventDefault();
    event.stopPropagation();
    if (event.type === "click") browser.TreeTabsService.toggleCollapsed(tab);
  }

  for (const type of ["mousedown", "click", "dblclick"]) {
    tabs.addEventListener(type, handleCollapsedDisclosure, { capture: true });
  }

  let paintedTreeRows = new Set();
  let treeFrame = 0;

  function paintTreeLines() {
    treeFrame = 0;
    const rows = tabs.hasAttribute("expanded") || !tabs.verticalMode
      ? []
      : tabs.visibleTabs.filter(tab => tab.hasAttribute("data-tree-level") &&
          !tab.hasAttribute("data-tree-hidden") && !tab.closing && !tab.pinned);
    const indices = new Map(rows.map((tab, index) => [tab.linkedPanel, index]));
    const lastChildren = new Map();
    const tracks = rows.map(() => [0, 0, 0]);
    for (const [index, tab] of rows.entries()) {
      const parent = indices.get(tab.dataset.treeParent);
      if (parent < index) lastChildren.set(parent, index);
    }

    // Each branch starts at its parent's center and ends at the last visible child's center.
    for (const [parent, last] of lastChildren) {
      const depth = Math.min(Number(rows[parent].dataset.treeLevel), 2);
      tracks[parent][depth] |= 2;
      for (let row = parent + 1; row < last; row++) tracks[row][depth] |= 3;
      tracks[last][depth] |= 1;
    }

    const nextPainted = new Set();
    for (const [index, tab] of rows.entries()) {
      const lines = tracks[index].flatMap((track, depth) => {
        if (!track) return [];
        const edge = track === 2 ? "bottom" : "top";
        const height = track === 3 ? "100%" : "50%";
        return `linear-gradient(currentColor 0 0) var(--textfox-tree-side) ${2 + depth * 2}px ${edge} 0 / 1px ${height} no-repeat`;
      });
      if (!lines.length) continue;
      tab.style.setProperty("--textfox-tree-lines", lines.join(", "));
      tab.setAttribute("textfox-tree-line", "");
      nextPainted.add(tab);
    }
    for (const tab of paintedTreeRows) {
      if (nextPainted.has(tab)) continue;
      tab.style.removeProperty("--textfox-tree-lines");
      tab.removeAttribute("textfox-tree-line");
    }
    paintedTreeRows = nextPainted;
  }

  const treeObserver = new MutationObserver(() => {
    if (!treeFrame) treeFrame = window.requestAnimationFrame(paintTreeLines);
  });
  treeObserver.observe(tabs, {
    subtree: true,
    childList: true,
    attributeFilter: ["expanded", "orient", "data-tree-level", "data-tree-parent", "data-tree-hidden",
      "hidden", "collapsed", "closing"],
  });
  treeFrame = window.requestAnimationFrame(paintTreeLines);
  window.addUnloadListener?.(() => {
    treeObserver.disconnect();
    window.cancelAnimationFrame(treeFrame);
  });

  function getMove(tab, direction) {
    if (!tab?.visible || tab.closing || tab.multiselected) return null;

    const tree = browser.TreeTabsService;
    const treeDrag = window.TreeTabsDnD;
    if (!tab.pinned && treeDrag?._isEnabled?.(tabs)) {
      if (typeof treeDrag._syncSubtreeStripPosition !== "function") return null;
      const node = treeDrag._getLogicalTab(tab);
      const parent = tree.getParent(node);
      const peers = parent ? tree.getChildren(parent) : tree.getRootTabs(window);
      const index = peers.indexOf(node);
      if (index < 0) return null;
      const neighbor = peers[index + direction];
      if (!neighbor?.visible || neighbor.closing || neighbor.pinned || neighbor.group !== node.group) {
        return null;
      }
      return () => {
        tree.moveTabSubtree(node, index + direction);
        treeDrag._syncSubtreeStripPosition(node);
      };
    }

    const element = tab.splitview || tab;
    const peers = [...new Set(tabs.visibleTabs.filter(other => other.pinned === tab.pinned)
      .map(other => other.splitview || other))];
    const index = peers.indexOf(element);
    const neighbor = index >= 0 ? peers[index + direction] : null;
    if (!neighbor || neighbor.parentNode !== element.parentNode || neighbor.closing) return null;
    return () => {
      if (direction < 0) browser.moveTabsBefore([element], neighbor);
      else browser.moveTabsAfter([element], neighbor);
    };
  }

  function getContextMove(direction) {
    const context = window.TabContextMenu;
    return context?.multiselected ? null : getMove(context?.contextTab, direction);
  }

  function getParentChoices() {
    const context = window.TabContextMenu;
    const tab = context?.contextTab;
    const drag = window.TreeTabsDnD;
    if (!tab?.visible || tab.closing || tab.pinned || context.multiselected ||
        !drag?._isEnabled?.(tabs) || typeof drag._syncSubtreeStripPosition !== "function") {
      return [];
    }

    const tree = browser.TreeTabsService;
    const child = drag._getLogicalTab(tab);
    const currentParent = tree.getParent(child);
    const descendants = new Set(tree.getDescendants(child));
    const state = tree._getStateForTab?.(child)?.state;
    return tabs.visibleTabs.filter(parent =>
      parent !== child && parent !== currentParent && drag._getLogicalTab(parent) === parent &&
      !parent.closing && !parent.pinned && parent.group === child.group && !descendants.has(parent) &&
      !(state && tree._wouldExceedMaxDepth?.(state, parent, child))
    );
  }

  const items = [-1, 1].map((direction, index) => {
    const backward = direction < 0;
    const item = document.createXULElement("menuitem");
    item.id = backward ? "textfox-move-tab-back" : "textfox-move-tab-forward";
    item.addEventListener("command", () => getContextMove(direction)?.());

    // The browser already dispatches Ctrl+Shift+Page Up/Down to these methods.
    const method = backward ? "moveTabBackward" : "moveTabForward";
    const nativeMove = browser[method];
    if (typeof nativeMove === "function") {
      const moveSelected = () => getMove(browser.selectedTab, direction)?.();
      browser[method] = moveSelected;
      window.addUnloadListener?.(() => {
        if (browser[method] === moveSelected) browser[method] = nativeMove;
      });

      const key = document.createXULElement("key");
      key.setAttribute("modifiers", "control,shift");
      key.setAttribute("keycode", backward ? "VK_PAGE_UP" : "VK_PAGE_DOWN");
      item.setAttribute("acceltext", ShortcutUtils.prettifyShortcut(key));
    }

    firstNativeItem.before(item);
    return { item, index, direction };
  });

  const attachMenu = document.createXULElement("menu");
  attachMenu.id = "textfox-attach-tab";
  attachMenu.hidden = true;
  attachMenu.setAttribute("label", portuguese ? "Tornar filha de" : "Make Child of");
  const attachPopup = document.createXULElement("menupopup");
  attachMenu.append(attachPopup);
  firstNativeItem.before(attachMenu);

  attachPopup.addEventListener("popupshowing", event => {
    if (event.target !== attachPopup) return;
    const child = window.TreeTabsDnD?._getLogicalTab(window.TabContextMenu?.contextTab);
    attachPopup.replaceChildren(...getParentChoices().map(parent => {
      const item = document.createXULElement("menuitem");
      const title = parent.label;
      item.setAttribute("label", title.length > 80 ? title.slice(0, 79) + "…" : title);
      item.setAttribute("tooltiptext", title);
      item.addEventListener("command", () => {
        const drag = window.TreeTabsDnD;
        if (drag?._getLogicalTab(window.TabContextMenu?.contextTab) !== child ||
            !getParentChoices().includes(parent)) return;
        if (browser.TreeTabsService.attachTab(child, parent)) drag._syncSubtreeStripPosition(child);
      });
      return item;
    }));
  });
  attachPopup.addEventListener("popuphidden", event => {
    if (event.target === attachPopup) attachPopup.replaceChildren();
  });

  menu.addEventListener("popupshowing", event => {
    if (event.target !== menu) return;
    const tab = window.TabContextMenu?.contextTab;
    const grid = tab?.pinned && tabs.isContainerVerticalPinnedGrid?.(tab);
    const wording = tabs.verticalMode && !grid ? labels.vertical : labels.ordered;
    for (const { item, index, direction } of items) {
      item.setAttribute("label", wording[index]);
      item.disabled = !getContextMove(direction);
    }
    attachMenu.hidden = !window.TreeTabsDnD?._isEnabled?.(tabs);
    attachMenu.disabled = !getParentChoices().length;
  });
})();
