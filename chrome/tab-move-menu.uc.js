(() => {
  "use strict";

  const browser = window.gBrowser;
  const menu = document.getElementById("moveTabOptionsMenu");
  const firstNativeItem = document.getElementById("context_moveToStart");
  if (!browser || !menu || !firstNativeItem || document.getElementById("textfox-move-tab-back")) {
    return;
  }

  const tabs = browser.tabContainer;
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

  function getMove(direction) {
    const context = window.TabContextMenu;
    const tab = context?.contextTab;
    if (!tab?.visible || tab.closing || context.multiselected) return null;

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

  const items = [-1, 1].map((direction, index) => {
    const item = document.createXULElement("menuitem");
    item.id = direction < 0 ? "textfox-move-tab-back" : "textfox-move-tab-forward";
    item.addEventListener("command", () => getMove(direction)?.());
    firstNativeItem.before(item);
    return { item, index, direction };
  });

  menu.addEventListener("popupshowing", event => {
    if (event.target !== menu) return;
    const tab = window.TabContextMenu?.contextTab;
    const grid = tab?.pinned && tabs.isContainerVerticalPinnedGrid?.(tab);
    const wording = tabs.verticalMode && !grid ? labels.vertical : labels.ordered;
    for (const { item, index, direction } of items) {
      item.setAttribute("label", wording[index]);
      item.disabled = !getMove(direction);
    }
  });
})();
