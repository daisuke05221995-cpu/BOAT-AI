from pathlib import Path

MAIN = Path("app/src/main/java/jp/boatai/app/MainActivity.kt")
VM = Path("app/src/main/java/jp/boatai/app/BoatViewModel.kt")


def find_index(lines, predicate, start=0):
    for i in range(start, len(lines)):
        if predicate(lines[i]):
            return i
    raise RuntimeError("target line not found")


def navigation_block_bounds(lines, selected_tab):
    selected = find_index(lines, lambda x: x.strip() == f"selected = ui.tab == {selected_tab},")
    start = selected
    while start >= 0 and lines[start].strip() != "NavigationBarItem(":
        start -= 1
    if start < 0:
        raise RuntimeError(f"navigation start not found for tab {selected_tab}")
    depth = 0
    end = start
    for i in range(start, len(lines)):
        depth += lines[i].count("(") - lines[i].count(")")
        if i > start and depth == 0:
            end = i
            break
    return start, end


def nav_item(indent, tab, icon, label):
    return [
        f"{indent}NavigationBarItem(\n",
        f"{indent}    selected = ui.tab == {tab},\n",
        f"{indent}    onClick = {{ vm.setTab({tab}) }},\n",
        f"{indent}    icon = {{ Icon(Icons.Default.{icon}, contentDescription = null) }},\n",
        f"{indent}    label = {{ Text(\"{label}\") }}\n",
        f"{indent})\n",
    ]


def patch_main():
    text = MAIN.read_text()
    if "PurchaseDashboardScreen(ui, vm)" in text and "ShoppingCart" in text:
        print("MainActivity already patched")
        return False

    lines = text.splitlines(keepends=True)

    # Import shopping cart icon.
    refresh_idx = find_index(lines, lambda x: x.strip() == "import androidx.compose.material.icons.filled.Refresh")
    if not any("filled.ShoppingCart" in x for x in lines):
        lines.insert(refresh_idx + 1, "import androidx.compose.material.icons.filled.ShoppingCart\n")

    # Top title mapping.
    result_title = find_index(lines, lambda x: x.strip() == 'ui.tab == 1 -> "結果"')
    indent = lines[result_title][: len(lines[result_title]) - len(lines[result_title].lstrip())]
    lines[result_title:result_title + 1] = [
        f'{indent}ui.tab == 1 -> "購入"\n',
        f'{indent}ui.tab == 2 -> "結果"\n',
    ]

    # Refresh button should work on prediction/purchase/results.
    for i, line in enumerate(lines):
        if "ui.tab in 0..1" in line:
            lines[i] = line.replace("ui.tab in 0..1", "ui.tab in 0..2")
            break

    # Replace the old result nav item with Purchase + Results.
    start, end = navigation_block_bounds(lines, 1)
    nav_indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
    lines[start:end + 1] = (
        nav_item(nav_indent, 1, "ShoppingCart", "購入")
        + nav_item(nav_indent, 2, "CheckCircle", "結果")
    )

    # Existing profit item moves from tab 2 to 3. Find by label to avoid picking new results.
    profit_label = find_index(lines, lambda x: x.strip() == 'label = { Text("損益") }')
    pstart = profit_label
    while pstart >= 0 and lines[pstart].strip() != "NavigationBarItem(":
        pstart -= 1
    if pstart < 0:
        raise RuntimeError("profit navigation block not found")
    for i in range(pstart, profit_label + 1):
        if "selected = ui.tab == 2," in lines[i]:
            lines[i] = lines[i].replace("ui.tab == 2", "ui.tab == 3")
        if "onClick = { vm.setTab(2) }," in lines[i]:
            lines[i] = lines[i].replace("vm.setTab(2)", "vm.setTab(3)")

    # Main screen routing.
    route0 = find_index(lines, lambda x: x.strip() == "ui.tab == 0 -> PredictionScreen(ui, vm)")
    if lines[route0 + 1].strip() != "ui.tab == 1 -> ResultsScreen(ui, vm)":
        raise RuntimeError("unexpected results route")
    if lines[route0 + 2].strip() != "else -> ProfitScreen(ui, vm)":
        raise RuntimeError("unexpected profit route")
    route_indent = lines[route0][: len(lines[route0]) - len(lines[route0].lstrip())]
    lines[route0:route0 + 3] = [
        f"{route_indent}ui.tab == 0 -> PredictionScreen(ui, vm)\n",
        f"{route_indent}ui.tab == 1 -> PurchaseDashboardScreen(ui, vm)\n",
        f"{route_indent}ui.tab == 2 -> CompactResultsScreen(ui, vm)\n",
        f"{route_indent}else -> CompactProfitScreen(ui, vm)\n",
    ]

    # Remove duplicate pending-purchase card from the top-level prediction list only.
    pred_start = find_index(lines, lambda x: x.strip() == "private fun PredictionScreen(ui: BoatUiState, vm: BoatViewModel) {")
    app_update = find_index(lines, lambda x: "AppUpdateCard(ui.update, vm)" in x, start=pred_start)
    for i in range(app_update + 1, min(app_update + 5, len(lines))):
        if "ui.pendingPurchase?.let" in lines[i] and "PendingPurchaseCard" in lines[i]:
            del lines[i]
            break

    MAIN.write_text("".join(lines))
    print("Patched MainActivity.kt")
    return True


def patch_vm():
    text = VM.read_text()
    if "tab = tab.coerceIn(0, 3)" in text:
        print("BoatViewModel already patched")
        return False
    old = "tab = tab.coerceIn(0, 2)"
    if old not in text:
        raise RuntimeError("setTab range not found")
    VM.write_text(text.replace(old, "tab = tab.coerceIn(0, 3)", 1))
    print("Patched BoatViewModel.kt")
    return True


if __name__ == "__main__":
    changed = patch_main() | patch_vm()
    print("changed=", changed)
