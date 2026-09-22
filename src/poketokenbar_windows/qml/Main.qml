import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Layouts

Rectangle {
    id: root
    width: 560
    height: 740
    color: appModel.darkMode ? "#0d121b" : "#f4f7fb"
    border.color: root.borderColor
    border.width: 1

    property int currentPage: 0
    property int trendHoveredIndex: -1
    property string collectionMode: "dex"
    property int selectedDexIndex: -1
    readonly property var selectedDex: selectedDexIndex >= 0 && selectedDexIndex < appModel.dexBrowseEntries.length
        ? appModel.dexBrowseEntries[selectedDexIndex] : ({})
    onCollectionModeChanged: if (collectionMode !== "dex") selectedDexIndex = -1

    function openDex(speciesId) {
        for (let index = 0; index < appModel.dexBrowseEntries.length; ++index) {
            if (appModel.dexBrowseEntries[index].speciesId === speciesId) {
                selectedDexIndex = index
                collectionPage.contentItem.contentY = 0
                return
            }
        }
    }

    function closeDex() {
        if (selectedDexIndex >= 0)
            appModel.moveDexPage(Math.floor(selectedDexIndex / 24) + 1 - appModel.dexPage)
        selectedDexIndex = -1
        collectionPage.contentItem.contentY = 0
    }
    readonly property bool darkMode: appModel.darkMode
    property color textColor: appModel.darkMode ? "#edf2ff" : "#172033"
    property color mutedColor: appModel.darkMode ? "#b9c7db" : "#5b6a80"
    property color panelColor: appModel.darkMode ? "#18212e" : "#ffffff"
    property color panelAltColor: appModel.darkMode ? "#202b3b" : "#edf3ff"
    property color borderColor: appModel.darkMode ? "#2b394e" : "#dce3ed"
    property color accentColor: appModel.darkMode ? "#8facff" : "#315da8"
    property color accentSurface: appModel.darkMode ? "#263754" : "#dbe7fb"
    property color successColor: appModel.darkMode ? "#75d6a7" : "#237a55"
    property color warningColor: appModel.darkMode ? "#f0bc68" : "#a45b00"
    property color dangerColor: appModel.darkMode ? "#ff9494" : "#b52c3b"

    function format(template, values) {
        let result = template
        for (const key in values)
            result = result.replace("{" + key + "}", values[key])
        return result
    }

    function revealKeyboardFocus() {
        const item = root.Window.window ? root.Window.window.activeFocusItem : null
        if (!item) return
        for (const page of [collectionPage, bagPage, shopPage, settingsPage]) {
            let ancestor = item
            while (ancestor && ancestor !== page) ancestor = ancestor.parent
            if (ancestor === page && page.visible) {
                page.revealItem(item)
                return
            }
        }
    }

    Connections {
        target: root.Window.window
        function onActiveFocusItemChanged() { Qt.callLater(root.revealKeyboardFocus) }
    }

    Popup {
        id: useItemPopup
        objectName: "useItemPopup"
        property string itemKind: ""
        function confirm(kind) { itemKind = kind; open() }
        parent: Overlay.overlay
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        width: Math.min(370, root.width - 32)
        height: 158
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 16
        Overlay.modal: Rectangle { color: "#80000000" }
        background: Rectangle { color: root.panelColor; radius: 12; border.color: root.borderColor; border.width: 1 }
        contentItem: ColumnLayout {
            spacing: 11
            Text { text: appModel.strings.use_item_title; color: root.textColor; font.pixelSize: 17; font.weight: Font.DemiBold }
            Text {
                Layout.fillWidth: true
                text: root.format(appModel.strings.use_item_question, {item: useItemPopup.itemKind === "rare_candy" ? appModel.strings.rare_candy : appModel.strings.mint})
                color: root.mutedColor
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                spacing: 8
                AppButton { text: appModel.strings.cancel; onClicked: useItemPopup.close() }
                AppButton {
                    text: appModel.strings.confirm_use
                    highlighted: true
                    onClicked: {
                        const kind = useItemPopup.itemKind
                        useItemPopup.close()
                        appModel.useItem(kind)
                        root.currentPage = 0
                    }
                }
            }
        }
    }

    component PageScroll: ScrollView {
        function revealItem(item) {
            const flickable = contentItem
            const position = item.mapToItem(flickable.contentItem, 0, 0)
            const bottom = position.y + item.height + 10
            let nextY = flickable.contentY
            if (position.y - 10 < nextY) nextY = position.y - 10
            else if (bottom > nextY + availableHeight) nextY = bottom - availableHeight
            flickable.contentY = Math.max(0, Math.min(nextY, flickable.contentHeight - availableHeight))
        }
    }

    component FocusFrame: Rectangle {
        anchors.fill: parent
        anchors.margins: -2
        visible: parent.activeFocus
        color: "transparent"
        radius: 6
        border.width: 2
        border.color: root.accentColor
        z: 10
    }

    component PokeBall: Item {
        implicitWidth: 24
        implicitHeight: 24
        Canvas {
            anchors.fill: parent
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                const size = Math.min(width, height)
                const cx = width / 2
                const cy = height / 2
                const radius = size / 2 - 1.2
                const outline = "#151922"

                ctx.save()
                ctx.beginPath()
                ctx.arc(cx, cy, radius, 0, 2 * Math.PI)
                ctx.clip()
                ctx.fillStyle = "#ffffff"
                ctx.fillRect(cx - radius, cy, radius * 2, radius)
                ctx.fillStyle = "#ef4455"
                ctx.fillRect(cx - radius, cy - radius, radius * 2, radius)
                ctx.restore()

                ctx.strokeStyle = outline
                ctx.lineWidth = Math.max(1.6, size * 0.08)
                ctx.beginPath()
                ctx.arc(cx, cy, radius, 0, 2 * Math.PI)
                ctx.stroke()
                ctx.fillStyle = outline
                ctx.fillRect(cx - radius, cy - size * 0.075, radius * 2, size * 0.15)
                ctx.beginPath()
                ctx.arc(cx, cy, size * 0.20, 0, 2 * Math.PI)
                ctx.fill()
                ctx.fillStyle = "#ffffff"
                ctx.beginPath()
                ctx.arc(cx, cy, size * 0.105, 0, 2 * Math.PI)
                ctx.fill()
            }
        }
    }

    component WarningIcon: Item {
        property color markColor: root.warningColor
        implicitWidth: 16
        implicitHeight: 16
        Accessible.ignored: true
        Canvas {
            anchors.fill: parent
            property color iconColor: parent.markColor
            onIconColorChanged: requestPaint()
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                const scale = Math.min(width, height) / 16
                ctx.save()
                ctx.scale(scale, scale)
                ctx.fillStyle = iconColor
                ctx.beginPath()
                ctx.moveTo(8, 1)
                ctx.lineTo(15, 14)
                ctx.quadraticCurveTo(15.4, 15, 14.1, 15)
                ctx.lineTo(1.9, 15)
                ctx.quadraticCurveTo(0.6, 15, 1, 14)
                ctx.closePath()
                ctx.fill()
                ctx.fillStyle = root.darkMode ? "#172033" : "#ffffff"
                ctx.fillRect(7.25, 5, 1.5, 5.5)
                ctx.beginPath()
                ctx.arc(8, 12.5, 1, 0, 2 * Math.PI)
                ctx.fill()
                ctx.restore()
            }
        }
    }

    component EggIcon: Item {
        required property string tier
        implicitWidth: 42
        implicitHeight: 42
        Canvas {
            anchors.fill: parent
            property string eggTier: parent.tier
            onEggTierChanged: requestPaint()
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                const scale = Math.min(width / 42, height / 42)
                ctx.save()
                ctx.scale(scale, scale)
                const fill = eggTier === "rare" ? "#936fe2"
                    : (eggTier === "uncommon" ? "#58a7e8" : "#faf8ef")
                const spots = eggTier === "rare" ? "#f2c653"
                    : (eggTier === "uncommon" ? "#d8f2ff" : "#c7ccd5")
                const outline = eggTier === "rare" ? "#352253"
                    : (eggTier === "uncommon" ? "#173b61" : "#30343b")

                ctx.fillStyle = fill
                ctx.strokeStyle = outline
                ctx.lineWidth = 2
                ctx.beginPath()
                ctx.moveTo(21, 3)
                ctx.bezierCurveTo(14, 3, 8, 17, 8, 27)
                ctx.bezierCurveTo(8, 36, 13, 40, 21, 40)
                ctx.bezierCurveTo(29, 40, 34, 36, 34, 27)
                ctx.bezierCurveTo(34, 17, 28, 3, 21, 3)
                ctx.closePath()
                ctx.fill()
                ctx.stroke()

                ctx.fillStyle = spots
                for (const spot of [[15, 23, 2.2], [25, 15, 1.8], [26, 30, 2.4]]) {
                    ctx.beginPath()
                    ctx.arc(spot[0], spot[1], spot[2], 0, 2 * Math.PI)
                    ctx.fill()
                }
                if (eggTier === "uncommon") {
                    ctx.fillStyle = "#e8fbff"
                    ctx.beginPath()
                    ctx.moveTo(34, 5); ctx.lineTo(36, 9); ctx.lineTo(40, 11)
                    ctx.lineTo(36, 13); ctx.lineTo(34, 17); ctx.lineTo(32, 13)
                    ctx.lineTo(28, 11); ctx.lineTo(32, 9); ctx.closePath(); ctx.fill()
                } else if (eggTier === "rare") {
                    ctx.fillStyle = "#ffd96a"
                    ctx.beginPath()
                    ctx.moveTo(34, 3); ctx.lineTo(36, 8); ctx.lineTo(41, 10)
                    ctx.lineTo(36, 12); ctx.lineTo(34, 17); ctx.lineTo(32, 12)
                    ctx.lineTo(27, 10); ctx.lineTo(32, 8); ctx.closePath(); ctx.fill()
                }
                ctx.restore()
            }
        }
    }

    component RepresentativeCheck: Rectangle {
        required property string label
        implicitWidth: 26
        implicitHeight: 26
        radius: 13
        color: root.successColor
        border.color: root.panelColor
        border.width: 2
        Accessible.name: label
        Canvas {
            anchors.centerIn: parent
            width: 14
            height: 14
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                ctx.strokeStyle = "#ffffff"
                ctx.lineWidth = 2.2
                ctx.lineCap = "round"
                ctx.lineJoin = "round"
                ctx.beginPath()
                ctx.moveTo(2, 7)
                ctx.lineTo(6, 11)
                ctx.lineTo(12, 3)
                ctx.stroke()
            }
        }
        HoverHandler { id: representativeHover }
        ToolTip.visible: representativeHover.hovered
        ToolTip.text: label
    }

    component Panel: Rectangle {
        color: root.panelColor
        radius: 11
        border.color: root.borderColor
        border.width: 1
    }

    component BagItemCard: Panel {
        id: bagCard
        property string itemKind: ""
        property string itemName: ""
        property string icon: ""
        property string description: ""
        property string effectHint: ""
        property string unavailableReason: ""
        property int count: 0
        property bool passive: false
        property bool canUse: false
        Layout.fillWidth: true
        Layout.preferredHeight: 98
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 10
            spacing: 5
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Text {
                    Layout.preferredWidth: 30
                    Layout.alignment: Qt.AlignTop
                    text: bagCard.icon
                    font.pixelSize: 25
                    horizontalAlignment: Text.AlignHCenter
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    RowLayout {
                        spacing: 6
                        Text { text: bagCard.itemName; color: root.textColor; font.pixelSize: 14; font.weight: Font.DemiBold }
                        Text {
                            visible: !bagCard.passive
                            text: "×" + bagCard.count
                            color: root.mutedColor
                            font.pixelSize: 11
                            font.weight: Font.Bold
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: bagCard.description
                        color: root.mutedColor
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Text {
                    Layout.fillWidth: true
                    text: bagCard.passive || bagCard.canUse ? bagCard.effectHint : bagCard.unavailableReason
                    color: bagCard.passive ? root.successColor : root.mutedColor
                    font.pixelSize: 10
                    font.weight: bagCard.passive ? Font.DemiBold : Font.Normal
                    wrapMode: Text.WordWrap
                }
                AppButton {
                    visible: !bagCard.passive && bagCard.canUse
                    text: appModel.strings.bag_use
                    accessibleName: bagCard.itemName + ": " + text
                    implicitHeight: 27
                    leftPadding: 10
                    rightPadding: 10
                    onClicked: useItemPopup.confirm(bagCard.itemKind)
                }
            }
        }
    }

    component InfoLabel: Text {
        required property string helpText
        color: root.textColor
        font.pixelSize: 12
        HoverHandler { id: infoHover }
        ToolTip.visible: infoHover.hovered
        ToolTip.delay: 550
        ToolTip.text: helpText
        Accessible.description: helpText
    }

    component StyledComboBox: ComboBox {
        id: styledCombo
        implicitHeight: 38
        implicitWidth: 144
        background: Rectangle {
            radius: 8
            color: root.panelAltColor
            border.color: styledCombo.activeFocus ? root.accentColor : root.borderColor
            border.width: styledCombo.activeFocus ? 2 : 1
        }
        contentItem: Text {
            leftPadding: 11
            rightPadding: 24
            text: styledCombo.displayText
            color: root.textColor
            font.pixelSize: 12
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
        indicator: Canvas {
            width: 16
            height: 16
            x: styledCombo.width - width - 10
            y: (styledCombo.height - height) / 2
            property color strokeColor: root.mutedColor
            onStrokeColorChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                ctx.strokeStyle = strokeColor
                ctx.lineWidth = 1.8
                ctx.lineCap = "round"
                ctx.lineJoin = "round"
                ctx.beginPath()
                ctx.moveTo(3, 6)
                ctx.lineTo(8, 11)
                ctx.lineTo(13, 6)
                ctx.stroke()
            }
        }
        delegate: ItemDelegate {
            required property var modelData
            width: styledCombo.width
            contentItem: Text {
                text: typeof modelData === "object"
                    ? (modelData.label || modelData.display || "")
                    : String(modelData)
                color: root.textColor
                font.pixelSize: 12
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                color: parent.hovered || parent.highlighted ? root.accentSurface : root.panelColor
            }
        }
        popup: Popup {
            y: styledCombo.height - 1
            width: styledCombo.width
            implicitHeight: Math.min(260, contentItem.implicitHeight + 6)
            padding: 3
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: styledCombo.popup.visible ? styledCombo.delegateModel : null
                currentIndex: styledCombo.highlightedIndex
                boundsBehavior: Flickable.StopAtBounds
            }
            background: Rectangle {
                color: root.panelColor
                radius: 8
                border.color: root.borderColor
            }
        }
    }

    component StyledSpinBox: SpinBox {
        id: styledSpin
        implicitWidth: 88
        implicitHeight: 36
        background: Rectangle {
            color: root.panelAltColor
            radius: 8
            border.color: styledSpin.activeFocus ? root.accentColor : root.borderColor
            border.width: styledSpin.activeFocus ? 2 : 1
        }
        contentItem: Text {
            text: styledSpin.textFromValue(styledSpin.value, styledSpin.locale)
            color: root.textColor
            font.pixelSize: 12
            leftPadding: 10
            rightPadding: 30
            verticalAlignment: Text.AlignVCenter
        }
        up.indicator: Item {
            x: styledSpin.width - 28
            y: 1
            width: 27
            height: 17
            Canvas {
                anchors.centerIn: parent
                width: 12
                height: 12
                property color strokeColor: styledSpin.up.pressed ? root.accentColor : root.textColor
                onStrokeColorChanged: requestPaint()
                onPaint: {
                    const ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    ctx.strokeStyle = strokeColor
                    ctx.lineWidth = 1.5
                    ctx.beginPath()
                    ctx.moveTo(2, 6)
                    ctx.lineTo(10, 6)
                    ctx.moveTo(6, 2)
                    ctx.lineTo(6, 10)
                    ctx.stroke()
                }
            }
        }
        down.indicator: Item {
            x: styledSpin.width - 28
            y: 18
            width: 27
            height: 17
            Canvas {
                anchors.centerIn: parent
                width: 12
                height: 12
                property color strokeColor: styledSpin.down.pressed ? root.accentColor : root.textColor
                onStrokeColorChanged: requestPaint()
                onPaint: {
                    const ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    ctx.strokeStyle = strokeColor
                    ctx.lineWidth = 1.5
                    ctx.beginPath()
                    ctx.moveTo(2, 6)
                    ctx.lineTo(10, 6)
                    ctx.stroke()
                }
            }
        }
    }

    component AppButton: Button {
        id: control
        property string accessibleName: text
        implicitHeight: 34
        leftPadding: 12
        rightPadding: 12
        activeFocusOnTab: true
        Accessible.name: accessibleName
        Accessible.role: Accessible.Button
        FocusFrame { }
        contentItem: Text {
            text: control.text
            color: control.enabled ? (control.highlighted ? "#ffffff" : root.textColor) : root.mutedColor
            font.pixelSize: 13
            font.weight: Font.Medium
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 7
            color: control.enabled
                ? (control.highlighted ? root.accentColor : (control.hovered ? root.accentSurface : root.panelAltColor))
                : (root.darkMode ? "#1a2230" : "#edf0f4")
            border.color: control.activeFocus ? root.accentColor : (control.highlighted ? "transparent" : root.borderColor)
            border.width: control.activeFocus ? 2 : 1
        }
    }

    component WindowButton: Button {
        id: windowControl
        required property string iconKind
        required property string helpText
        property bool closeStyle: false
        implicitWidth: 46
        implicitHeight: 34
        activeFocusOnTab: true
        Accessible.name: helpText
        Accessible.role: Accessible.Button
        ToolTip.visible: hovered || activeFocus
        ToolTip.delay: 500
        ToolTip.text: helpText
        contentItem: Canvas {
            id: windowGlyph
            objectName: windowControl.objectName + "Glyph"
            property string renderedKind: windowControl.iconKind
            onRenderedKindChanged: requestPaint()
            implicitWidth: 16
            implicitHeight: 16
            property color strokeColor: windowControl.closeStyle && windowControl.hovered
                ? "#ffffff" : root.textColor
            onStrokeColorChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                ctx.strokeStyle = strokeColor
                ctx.lineWidth = 1
                ctx.lineCap = "square"
                ctx.lineJoin = "miter"
                if (renderedKind === "minimize") {
                    ctx.beginPath()
                    ctx.moveTo(3.5, 11.5)
                    ctx.lineTo(12.5, 11.5)
                    ctx.stroke()
                } else if (renderedKind === "maximize") {
                    ctx.strokeRect(3.5, 3.5, 9, 9)
                } else if (renderedKind === "restore") {
                    ctx.strokeRect(3.5, 5.5, 7, 7)
                    ctx.beginPath()
                    ctx.moveTo(5.5, 5.5)
                    ctx.lineTo(5.5, 3.5)
                    ctx.lineTo(12.5, 3.5)
                    ctx.lineTo(12.5, 10.5)
                    ctx.lineTo(10.5, 10.5)
                    ctx.stroke()
                } else {
                    ctx.beginPath()
                    ctx.moveTo(4, 4)
                    ctx.lineTo(12, 12)
                    ctx.moveTo(12, 4)
                    ctx.lineTo(4, 12)
                    ctx.stroke()
                }
            }
        }
        background: Rectangle {
            color: windowControl.closeStyle && windowControl.hovered
                ? "#c42b1c"
                : (windowControl.hovered ? root.panelAltColor : "transparent")
        }
    }

    component ResizeHandle: MouseArea {
        required property int resizeEdges
        enabled: !appModel.windowMaximized
        acceptedButtons: Qt.LeftButton
        z: 100
        onPressed: appModel.startWindowResize(resizeEdges)
    }

    component NavButton: Button {
        id: nav
        required property int pageIndex
        required property string iconKind
        required property string description
        checkable: true
        checked: root.currentPage === pageIndex
        activeFocusOnTab: true
        Accessible.name: nav.text
        Accessible.description: nav.description
        Accessible.role: Accessible.PageTab
        ToolTip.visible: nav.hovered || nav.activeFocus
        ToolTip.delay: 550
        ToolTip.text: nav.description
        implicitHeight: 38
        onClicked: root.currentPage = pageIndex
        background: Rectangle {
            radius: 7
            color: nav.checked ? root.accentSurface : (nav.hovered ? root.panelAltColor : "transparent")
            border.color: nav.activeFocus ? root.accentColor : "transparent"
            border.width: nav.activeFocus ? 2 : 0
            Rectangle {
                visible: nav.checked
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 3
                radius: 2
                color: root.accentColor
            }
        }
        contentItem: RowLayout {
            spacing: root.width < 600 ? 3 : 6
            Item { Layout.fillWidth: true }
            Canvas {
                id: navIcon
                Layout.preferredWidth: 15
                Layout.preferredHeight: 15
                property color strokeColor: nav.checked ? root.textColor : root.mutedColor
                onStrokeColorChanged: requestPaint()
                onPaint: {
                    const ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    ctx.strokeStyle = strokeColor
                    ctx.fillStyle = strokeColor
                    ctx.lineWidth = 1.5
                    ctx.lineCap = "round"
                    ctx.lineJoin = "round"
                    if (nav.iconKind === "home") {
                        ctx.beginPath(); ctx.moveTo(2, 7); ctx.lineTo(7.5, 2); ctx.lineTo(13, 7)
                        ctx.moveTo(3.5, 6); ctx.lineTo(3.5, 13); ctx.lineTo(11.5, 13); ctx.lineTo(11.5, 6); ctx.stroke()
                    } else if (nav.iconKind === "collection") {
                        for (let x = 2; x <= 8; x += 6)
                            for (let y = 2; y <= 8; y += 6) ctx.strokeRect(x, y, 4, 4)
                    } else if (nav.iconKind === "bag") {
                        ctx.strokeRect(2.5, 5, 10, 8)
                        ctx.beginPath(); ctx.arc(7.5, 5, 3, Math.PI, 2 * Math.PI); ctx.stroke()
                    } else if (nav.iconKind === "shop") {
                        ctx.beginPath(); ctx.moveTo(1.5, 2.5); ctx.lineTo(3, 2.5); ctx.lineTo(4.2, 9.5)
                        ctx.lineTo(11.5, 9.5); ctx.lineTo(13, 4.5); ctx.lineTo(3.5, 4.5); ctx.stroke()
                        ctx.beginPath(); ctx.arc(5.5, 12.5, 1, 0, 2 * Math.PI); ctx.arc(10.5, 12.5, 1, 0, 2 * Math.PI); ctx.fill()
                    } else {
                        ctx.beginPath()
                        ctx.moveTo(2, 3); ctx.lineTo(13, 3); ctx.moveTo(2, 7.5); ctx.lineTo(13, 7.5)
                        ctx.moveTo(2, 12); ctx.lineTo(13, 12); ctx.stroke()
                        ctx.beginPath(); ctx.arc(5, 3, 1.6, 0, 2 * Math.PI)
                        ctx.arc(10, 7.5, 1.6, 0, 2 * Math.PI); ctx.arc(6.5, 12, 1.6, 0, 2 * Math.PI); ctx.fill()
                    }
                }
            }
            Text {
                text: nav.text
                color: nav.checked ? root.textColor : root.mutedColor
                font.pixelSize: root.width < 600 ? 11 : 12
                font.weight: nav.checked ? Font.Medium : Font.Normal
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
            }
            Item { Layout.fillWidth: true }
        }
    }



    component ModernProgress: Rectangle {
        id: progressTrack
        required property real value
        property color barColor: root.accentColor
        implicitHeight: 8
        radius: 4
        color: root.darkMode ? "#303c50" : "#dce3ee"
        clip: true
        Rectangle {
            width: Math.max(0, Math.min(parent.width, parent.width * progressTrack.value / 100))
            height: parent.height
            radius: parent.radius
            color: progressTrack.barColor
            Behavior on width { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
        }
    }

    component MetricCard: Panel {
        required property string label
        required property string value
        Layout.fillWidth: true
        Layout.preferredHeight: 56
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 9
            spacing: 1
            Text { text: label; color: root.mutedColor; font.pixelSize: 11 }
            Text { text: value; color: root.textColor; font.pixelSize: 16; font.weight: Font.DemiBold }
        }
    }

    component WalletBar: Rectangle {
        implicitHeight: 38
        color: root.panelColor
        border.color: root.borderColor
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 14
            spacing: 7
            Rectangle {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                radius: 9
                color: root.accentSurface
                border.color: root.accentColor
                Text { anchors.centerIn: parent; text: "•"; color: root.accentColor; font.pixelSize: 14; font.weight: Font.Bold }
            }
            Text { text: appModel.strings.wallet; color: root.mutedColor; font.pixelSize: 11 }
            Item { Layout.fillWidth: true }
            Text { text: appModel.wallet; color: root.textColor; font.pixelSize: 15; font.weight: Font.DemiBold }
        }
    }

    component ToggleRow: RowLayout {
        id: toggleRow
        required property string label
        property string detail: ""
        property alias checked: toggle.checked
        signal changed(bool value)
        Layout.fillWidth: true
        spacing: 12
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Text { text: toggleRow.label; color: root.textColor; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true }

        }
        HoverHandler { id: toggleHover }
        ToolTip.visible: (toggleHover.hovered || toggle.activeFocus) && toggleRow.detail.length > 0
        ToolTip.delay: 550
        ToolTip.text: toggleRow.detail
        Switch {
            id: toggle
            activeFocusOnTab: true
            Accessible.name: toggleRow.label
            Accessible.description: toggleRow.detail
            FocusFrame { }
            onToggled: toggleRow.changed(checked)
        }
    }

    component FilterChip: Button {
        id: chip
        required property string filterKey
        required property string label
        required property int itemCount
        checkable: true
        checked: appModel.dexFilter === filterKey
        activeFocusOnTab: true
        implicitHeight: 28
        implicitWidth: chipContent.implicitWidth + 18
        Accessible.name: root.format(appModel.strings.filter_by, {label: label})
        Accessible.role: Accessible.RadioButton
        onClicked: appModel.setDexFilter(filterKey)
        contentItem: RowLayout {
            id: chipContent
            spacing: 6
            Text {
                text: chip.label
                color: chip.checked ? root.textColor : root.mutedColor
                font.pixelSize: 11
                font.weight: chip.checked ? Font.Medium : Font.Normal
            }
            Rectangle {
                implicitWidth: Math.max(20, chipCount.implicitWidth + 10)
                implicitHeight: 18
                radius: 9
                color: chip.checked ? root.accentColor : root.panelColor
                Text {
                    id: chipCount
                    anchors.centerIn: parent
                    text: chip.itemCount
                    color: chip.checked ? "#ffffff" : root.mutedColor
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
            }
        }
        background: Rectangle {
            radius: 7
            color: chip.checked ? root.accentSurface : "transparent"
            border.color: chip.activeFocus ? root.accentColor : (chip.checked ? root.accentColor : root.borderColor)
            border.width: chip.activeFocus || chip.checked ? 2 : 1
        }
    }

    component SegmentedControl: Rectangle {
        id: segment
        required property var options
        required property string currentValue
        property string accessibleName: ""
        signal selected(string value)
        implicitHeight: 34
        implicitWidth: optionRow.implicitWidth + 6
        radius: 8
        color: root.panelAltColor
        border.color: root.borderColor
        RowLayout {
            id: optionRow
            anchors.fill: parent
            anchors.margins: 3
            spacing: 2
            Repeater {
                model: segment.options
                Button {
                    id: optionButton
                    required property var modelData
                    checkable: true
                    checked: segment.currentValue === modelData.value
                    activeFocusOnTab: true
                    implicitHeight: 28
                    leftPadding: 9
                    rightPadding: 9
                    Accessible.name: segment.accessibleName + ": " + modelData.label
                    Accessible.role: Accessible.RadioButton
                    onClicked: segment.selected(modelData.value)
                    contentItem: Text {
                        text: optionButton.modelData.label
                        color: optionButton.checked ? root.textColor : root.mutedColor
                        font.pixelSize: 12
                        font.weight: optionButton.checked ? Font.Medium : Font.Normal
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        radius: 5
                        color: optionButton.checked ? root.panelColor : "transparent"
                        border.color: optionButton.activeFocus ? root.accentColor : (optionButton.checked ? root.borderColor : "transparent")
                    }
                }
            }
        }
    }


    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: shellHeader
            Layout.fillWidth: true
            Layout.preferredHeight: 78
            color: root.panelColor
            border.color: root.borderColor
            ColumnLayout {
                anchors.fill: parent
                spacing: 0
                Item {
                    id: customTitleBar
                    objectName: "customTitleBar"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 36
                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.LeftButton
                        onPressed: appModel.startWindowMove()
                        onDoubleClicked: appModel.toggleMaximizeWindow()
                    }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        spacing: 7
                        PokeBall { objectName: "brandMark"; Layout.preferredWidth: 25; Layout.preferredHeight: 25 }
                        Text {
                            text: "PokeTokenBar"
                            color: root.textColor
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                        }
                        Rectangle {
                            Layout.leftMargin: 5
                            width: 7
                            height: 7
                            radius: 4
                            color: appModel.loading ? root.warningColor : root.successColor
                        }
                        Text {
                            text: appModel.statusText
                            color: root.mutedColor
                            font.pixelSize: 10
                            elide: Text.ElideRight
                            Layout.preferredWidth: Math.min(135, implicitWidth)
                            Layout.minimumWidth: 62
                            Layout.maximumWidth: 135
                        }
                        Item { Layout.fillWidth: true }
                        WindowButton {
                            objectName: "minimizeWindowButton"
                            iconKind: "minimize"
                            helpText: appModel.strings.window_minimize
                            onClicked: appModel.minimizeWindow()
                        }
                        WindowButton {
                            objectName: "maximizeWindowButton"
                            iconKind: appModel.windowMaximized ? "restore" : "maximize"
                            helpText: appModel.windowMaximized ? appModel.strings.window_restore : appModel.strings.window_maximize
                            onClicked: appModel.toggleMaximizeWindow()
                        }
                        WindowButton {
                            objectName: "closeWindowButton"
                            iconKind: "close"
                            helpText: appModel.strings.window_close
                            closeStyle: true
                            onClicked: appModel.closeWindow()
                        }
                    }
                }
                RowLayout {
                    objectName: "topNavigation"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    Layout.leftMargin: 10
                    Layout.rightMargin: 10
                    spacing: 2
                    NavButton { pageIndex: 0; iconKind: "home"; text: appModel.strings.nav_home; description: appModel.strings.home_description; Layout.fillWidth: true }
                    NavButton { pageIndex: 1; iconKind: "collection"; text: appModel.strings.nav_collection; description: appModel.strings.collection_description; Layout.fillWidth: true }
                    NavButton { pageIndex: 2; iconKind: "bag"; text: appModel.strings.nav_bag; description: appModel.strings.bag_description; Layout.fillWidth: true }
                    NavButton { pageIndex: 3; iconKind: "shop"; text: appModel.strings.nav_shop; description: appModel.strings.shop_description; Layout.fillWidth: true }
                    NavButton { pageIndex: 4; iconKind: "settings"; text: appModel.strings.nav_settings; description: appModel.strings.settings_description; Layout.fillWidth: true }
                }
            }
        }

        WalletBar {
            objectName: "sharedWalletBar"
            Layout.fillWidth: true
            visible: root.currentPage === 2 || root.currentPage === 3
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.currentPage

            Item {
                id: homePage
                objectName: "homePage"
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 7

                    Panel {
                        id: companionPanel
                        objectName: "companionPanel"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 158
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 11
                            spacing: 12
                            Rectangle {
                                objectName: "companionFrame"
                                Layout.preferredWidth: 136
                                Layout.preferredHeight: 136
                                radius: 12
                                color: root.accentSurface
                                AnimatedImage {
                                    objectName: "companionAnimation"
                                    anchors.fill: parent
                                    anchors.margins: 5
                                    source: appModel.spriteUrl
                                    fillMode: Image.PreserveAspectFit
                                    smooth: false
                                    playing: visible && root.currentPage === 0
                                    visible: !appModel.loading && !appModel.revealActive
                                }
                                PokeBall {
                                    id: revealBall
                                    objectName: "companionReveal"
                                    anchors.centerIn: parent
                                    width: 48; height: 48
                                    visible: appModel.loading || appModel.revealActive
                                    property int shakeFrame: 0
                                    transform: Translate {
                                        x: [0, -5, 5, -4, 4, -2, 2, 0][revealBall.shakeFrame] * revealBall.width / 96
                                        y: revealBall.height * 0.1
                                    }
                                    Timer {
                                        interval: 90
                                        running: revealBall.visible
                                        repeat: true
                                        onTriggered: revealBall.shakeFrame = (revealBall.shakeFrame + 1) % 8
                                    }
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { objectName: "companionName"; text: appModel.companionName; color: root.textColor; font.pixelSize: 24; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                                    AppButton {
                                        objectName: "homeRefreshButton"
                                        Layout.preferredHeight: 30
                                        text: appModel.strings.refresh
                                        accessibleName: appModel.strings.refresh
                                        highlighted: true
                                        enabled: appModel.refreshEnabled
                                        onClicked: appModel.requestRefresh()
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 5
                                    Text { text: appModel.companionSubtitle; color: root.mutedColor; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Rectangle {
                                        objectName: "growthBoostBadge"
                                        visible: appModel.growthBoost
                                        Layout.preferredWidth: 30
                                        Layout.preferredHeight: 18
                                        radius: 9
                                        color: root.darkMode ? "#503b22" : "#fff0d6"
                                        Text { anchors.centerIn: parent; text: appModel.strings.repeat_boost; color: root.warningColor; font.pixelSize: 10; font.weight: Font.Bold }
                                        HoverHandler { id: growthHover }
                                        ToolTip.visible: growthHover.hovered
                                        ToolTip.delay: 450
                                        ToolTip.text: appModel.strings.repeat_boost_help
                                        Accessible.name: appModel.strings.repeat_boost_help
                                    }
                                }
                                Text { objectName: "companionEvolution"; text: appModel.companionEvolutionText; color: appModel.darkMode ? "#96a5bc" : "#66758a"; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                                Item { Layout.fillHeight: true }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: appModel.companionProgressText; color: root.textColor; font.pixelSize: 12; Layout.fillWidth: true }
                                    Text { text: appModel.companionLevelText; color: root.textColor; font.pixelSize: 15; font.weight: Font.Bold }
                                }
                                ModernProgress { objectName: "companionProgressBar"; Layout.fillWidth: true; value: appModel.companionProgress }
                            }
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: width >= 720 ? 4 : 2
                        columnSpacing: 7
                        rowSpacing: 7
                        MetricCard { label: appModel.strings.tokens_today; value: appModel.todayTokens }
                        MetricCard { label: appModel.strings.estimated_cost; value: appModel.todayCost }
                        MetricCard { label: appModel.strings.this_week; value: appModel.weekTokens }
                        MetricCard { label: appModel.strings.wallet; value: appModel.wallet }
                    }

                    Panel {
                        id: trendPanel
                        objectName: "monthTrendPanel"
                        visible: appModel.monthTrend.length > 0
                        Layout.fillWidth: true
                        Layout.preferredHeight: visible ? 105 : 0
                        Layout.minimumHeight: Layout.preferredHeight
                        Layout.maximumHeight: Layout.preferredHeight
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 2
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: appModel.strings.month_trend; color: root.textColor; font.pixelSize: 13; font.weight: Font.DemiBold }
                                Item { Layout.fillWidth: true }
                                Text {
                                    text: appModel.monthTrend.length > 0
                                        ? appModel.monthTrend[root.trendHoveredIndex >= 0 ? Math.min(root.trendHoveredIndex, appModel.monthTrend.length - 1) : appModel.monthTrend.length - 1].caption : ""
                                    color: root.mutedColor
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                }
                            }
                            Row {
                                id: trendBars
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                spacing: 2
                                Repeater {
                                    model: appModel.monthTrend
                                    delegate: Item {
                                        required property var modelData
                                        required property int index
                                        width: Math.max(2, (trendBars.width - Math.max(0, appModel.monthTrend.length - 1) * trendBars.spacing) / Math.max(1, appModel.monthTrend.length))
                                        height: trendBars.height
                                        Rectangle {
                                            anchors.bottom: parent.bottom
                                            anchors.bottomMargin: 17
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            width: Math.max(3, parent.width - 2)
                                            height: modelData.barHeight
                                            radius: 2
                                            color: index === appModel.monthTrend.length - 1 ? root.accentColor : (root.darkMode ? "#6c8ed0" : "#90addd")
                                        }
                                        Rectangle {
                                            visible: modelData.weekend
                                            anchors.bottom: parent.bottom
                                            anchors.bottomMargin: 12
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            width: 2; height: 2; radius: 1
                                            color: root.mutedColor
                                        }
                                        Text {
                                            anchors.bottom: parent.bottom
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            text: modelData.label
                                            color: root.mutedColor
                                            font.pixelSize: 8
                                        }
                                        HoverHandler {
                                            id: trendHover
                                            onHoveredChanged: root.trendHoveredIndex = hovered ? index : -1
                                        }
                                        ToolTip.visible: trendHover.hovered
                                        ToolTip.text: modelData.caption
                                    }
                                }
                            }
                        }
                    }

                    Panel {
                        id: providersPanel
                        objectName: "providersPanel"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 16 + providersTitle.implicitHeight + 4 + Math.min(82, Math.max(26, appModel.providers.length * 28 - 2))
                        Layout.minimumHeight: Layout.preferredHeight
                        Layout.maximumHeight: Layout.preferredHeight
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 4
                            Text { id: providersTitle; text: appModel.strings.providers; color: root.textColor; font.pixelSize: 13; font.weight: Font.DemiBold }
                            ListView {
                                id: providersList
                                objectName: "providersList"
                                boundsBehavior: Flickable.StopAtBounds
                                interactive: contentHeight > height
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                spacing: 2
                                model: appModel.providers
                                ScrollBar.vertical: ScrollBar { policy: providersList.contentHeight > providersList.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff }
                                delegate: Rectangle {
                                    required property var modelData
                                    width: ListView.view.width
                                    height: 26
                                    radius: 6
                                    color: root.panelAltColor
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 8
                                        anchors.rightMargin: 8
                                        spacing: 6
                                        Text { text: modelData.name; color: modelData.error ? root.dangerColor : root.textColor; font.pixelSize: 11; font.weight: Font.Medium; Layout.preferredWidth: 74; elide: Text.ElideRight }
                                        Text { text: modelData.today + " " + appModel.strings.today_short; color: root.textColor; font.pixelSize: 10 }
                                        Text { text: modelData.week + " " + appModel.strings.week_short; color: root.mutedColor; font.pixelSize: 10 }
                                        Item { Layout.fillWidth: true }
                                        Text { text: modelData.cost; color: root.textColor; font.pixelSize: 10; font.weight: Font.Medium }
                                    }
                                }
                            }
                            Text { visible: appModel.providers.length === 0; text: appModel.strings.no_provider_data; color: root.mutedColor; font.pixelSize: 11 }
                        }
                    }

                    Panel {
                        id: limitsPanel
                        objectName: "limitsPanel"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 90
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 5
                            Text { text: appModel.strings.official_limits; color: root.textColor; font.pixelSize: 13; font.weight: Font.DemiBold }
                            ListView {
                                id: limitsContent
                                objectName: "limitsContent"
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                spacing: 5
                                model: appModel.limits
                                ScrollBar.vertical: ScrollBar { policy: limitsContent.contentHeight > limitsContent.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff }
                                delegate: Rectangle {
                                    required property var modelData
                                    width: ListView.view.width
                                    height: modelData.kind === "window" ? (modelData.forecast.length > 0 ? 61 : 49) : 38
                                    radius: 7
                                    color: modelData.kind === "credit"
                                        ? (modelData.urgency === "critical" ? (root.darkMode ? "#4a2328" : "#fff0f1") : (modelData.urgency === "warning" ? (root.darkMode ? "#48381f" : "#fff7e7") : root.accentSurface))
                                        : root.panelAltColor
                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 7
                                        spacing: 2
                                        RowLayout {
                                            Layout.fillWidth: true
                                            WarningIcon {
                                                objectName: "resetCreditWarningIcon"
                                                visible: modelData.kind === "credit" && modelData.urgency !== "neutral"
                                                markColor: modelData.urgency === "critical" ? root.dangerColor : root.warningColor
                                                Layout.preferredWidth: 16
                                                Layout.preferredHeight: 16
                                            }
                                            Text {
                                                text: modelData.kind === "credit"
                                                    ? modelData.provider + " · " + modelData.label
                                                    : modelData.provider + (modelData.plan.length ? " · " + modelData.plan : "") + " · " + modelData.label
                                                color: modelData.urgency === "critical" ? root.dangerColor : (modelData.urgency === "warning" ? root.warningColor : root.textColor)
                                                font.pixelSize: 11
                                                font.weight: modelData.kind === "credit" ? Font.DemiBold : Font.Medium
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                            }
                                            Text { visible: modelData.kind !== "credit"; text: modelData.percentText; color: root.textColor; font.pixelSize: 11; font.weight: Font.DemiBold }
                                        }
                                        RowLayout {
                                            visible: modelData.kind === "window"
                                            Layout.fillWidth: true
                                            Text { text: modelData.reset; color: root.mutedColor; font.pixelSize: 10; Layout.fillWidth: true }
                                            Text { visible: modelData.forecast.length > 0; text: appModel.strings.forecast + ": " + modelData.forecast; color: root.mutedColor; font.pixelSize: 10; elide: Text.ElideRight; Layout.maximumWidth: 230 }
                                        }
                                        ModernProgress {
                                            visible: modelData.kind === "window"
                                            Layout.fillWidth: true
                                            value: modelData.percent
                                            barColor: modelData.urgency === "critical" ? root.dangerColor : (modelData.urgency === "warning" ? root.warningColor : root.accentColor)
                                        }
                                    }
                                }
                            }
                            Text { visible: appModel.limits.length === 0; text: appModel.strings.no_limit_data; color: root.mutedColor; font.pixelSize: 11 }
                        }
                    }
                }
            }


            PageScroll {
                id: collectionPage
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: collectionPage.availableWidth
                    spacing: 10
                    Item { Layout.preferredHeight: 4 }
                    ColumnLayout {
                        id: collectionToolbar
                        objectName: "collectionToolbar"
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        spacing: 5
                        RowLayout {
                            objectName: "collectionModeControl"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 34
                            spacing: 14
                            Repeater {
                                model: [
                                    {label: appModel.strings.pokedex, value: "dex"},
                                    {label: appModel.strings.catch_log, value: "catches"}
                                ]
                                Button {
                                    id: collectionTab
                                    required property var modelData
                                    checkable: true
                                    checked: root.collectionMode === modelData.value
                                    activeFocusOnTab: true
                                    implicitHeight: 34
                                    leftPadding: 4
                                    rightPadding: 4
                                    Accessible.name: appModel.strings.collection_view + ": " + modelData.label
                                    Accessible.role: Accessible.PageTab
                                    onClicked: root.collectionMode = modelData.value
                                    contentItem: Text {
                                        text: collectionTab.modelData.label
                                        color: collectionTab.checked ? root.textColor : root.mutedColor
                                        font.pixelSize: 12
                                        font.weight: collectionTab.checked ? Font.DemiBold : Font.Normal
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    background: Item {
                                        Rectangle {
                                            visible: collectionTab.checked
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            anchors.bottom: parent.bottom
                                            height: 3
                                            radius: 2
                                            color: root.accentColor
                                        }
                                        Rectangle {
                                            visible: collectionTab.activeFocus
                                            anchors.fill: parent
                                            radius: 6
                                            color: "transparent"
                                            border.color: root.accentColor
                                            border.width: 2
                                        }
                                    }
                                }
                            }
                            Item { Layout.fillWidth: true }
                        }
                        RowLayout {
                            objectName: "dexFilterRow"
                            visible: root.collectionMode === "dex" && root.selectedDexIndex < 0
                            Layout.fillWidth: true
                            Layout.preferredHeight: 28
                            spacing: 8
                            Flow {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 28
                                spacing: 5
                                Repeater {
                                    model: appModel.dexFilters
                                    FilterChip {
                                        required property var modelData
                                        filterKey: modelData.key
                                        label: modelData.label
                                        itemCount: modelData.count
                                    }
                                }
                            }
                            Text {
                                objectName: "dexPagePosition"
                                text: root.format(appModel.strings.page, {page: appModel.dexPage, count: appModel.dexPageCount})
                                color: root.mutedColor
                                font.pixelSize: 11
                                Layout.alignment: Qt.AlignVCenter
                            }
                        }
                    }
                    Text {
                        visible: root.collectionMode === "dex" && root.selectedDexIndex < 0
                        Layout.leftMargin: 14
                        text: appModel.dexSummary
                        color: root.mutedColor
                        font.pixelSize: 11
                    }
                    GridLayout {
                        visible: root.collectionMode === "dex" && root.selectedDexIndex < 0
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        columns: width >= 720 ? 4 : (width >= 470 ? 3 : 2)
                        columnSpacing: 7
                        rowSpacing: 7
                        Repeater {
                            model: appModel.dexEntries
                            Panel {
                                id: dexCard
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: modelData.hasShiny ? 210 : 174
                                border.color: modelData.representative
                                    ? root.successColor
                                    : (dexCardButton.hovered ? root.accentColor : root.borderColor)
                                border.width: modelData.representative || dexCardButton.hovered ? 2 : 1
                                Button {
                                    id: dexCardButton
                                    anchors.fill: parent
                                    activeFocusOnTab: true
                                    Accessible.name: root.format(appModel.strings.dex_open, {name: modelData.name})
                                    Accessible.description: modelData.representative
                                        ? (modelData.followingCurrent ? appModel.strings.following_current : appModel.strings.representative_selected)
                                        : ""
                                    Accessible.role: Accessible.Button
                                    onClicked: root.openDex(modelData.speciesId)
                                    background: Item { }
                                    contentItem: Item { }
                                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                                    FocusFrame { }
                                }
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 8
                                    spacing: 2
                                    Image { source: modelData.sprite; Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: 108; Layout.preferredHeight: 108; fillMode: Image.PreserveAspectFit; smooth: false }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: modelData.number; color: root.mutedColor; font.pixelSize: 10 }
                                        Item { Layout.fillWidth: true }
                                        Text { visible: modelData.showShiny; text: "✨"; font.pixelSize: 11 }
                                    }
                                    Text { text: modelData.name; color: root.textColor; font.pixelSize: 12; font.weight: Font.Medium; elide: Text.ElideRight; Layout.fillWidth: true }
                                    AppButton {
                                        Layout.fillWidth: true
                                        visible: modelData.hasShiny
                                        text: modelData.showShiny ? "Normal" : "Shiny"
                                        accessibleName: root.format(modelData.showShiny ? appModel.strings.view_normal : appModel.strings.view_shiny, {name: modelData.name})
                                        onClicked: appModel.toggleDexVariant(modelData.speciesId)
                                    }
                                }
                                RepresentativeCheck {
                                    objectName: "representativeBadge"
                                    visible: modelData.representative
                                    anchors.top: parent.top
                                    anchors.right: parent.right
                                    anchors.margins: 8
                                    z: 4
                                    label: modelData.followingCurrent
                                        ? appModel.strings.following_current
                                        : appModel.strings.representative_selected
                                }
                            }
                        }
                    }
                    Text { visible: root.collectionMode === "dex" && root.selectedDexIndex < 0 && appModel.dexEntries.length === 0; Layout.leftMargin: 14; text: appModel.strings.empty_pokedex; color: root.mutedColor; font.pixelSize: 12 }
                    RowLayout {
                        visible: root.collectionMode === "dex" && root.selectedDexIndex < 0
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        AppButton { text: appModel.strings.previous; enabled: appModel.dexPage > 1; onClicked: appModel.moveDexPage(-1) }
                        Item { Layout.fillWidth: true }
                        AppButton { text: appModel.strings.next; enabled: appModel.dexPage < appModel.dexPageCount; onClicked: appModel.moveDexPage(1) }
                    }
                    Panel {
                        objectName: "dexDetailPanel"
                        visible: root.collectionMode === "dex" && root.selectedDexIndex >= 0
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        Layout.preferredHeight: appModel.representativeFollowsCurrent ? 388 : 426
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 5
                            RowLayout {
                                Layout.fillWidth: true
                                AppButton {
                                    text: appModel.strings.dex_back
                                    onClicked: root.closeDex()
                                }
                                Item { Layout.fillWidth: true }
                                Text {
                                    text: root.format(appModel.strings.dex_position, {
                                        position: root.selectedDexIndex + 1,
                                        count: appModel.dexBrowseEntries.length
                                    })
                                    color: root.mutedColor
                                    font.pixelSize: 13
                                }
                            }
                            AnimatedImage {
                                objectName: "dexDetailAnimation"
                                Layout.alignment: Qt.AlignHCenter
                                Layout.fillWidth: true
                                Layout.preferredHeight: 216
                                source: root.selectedDex.animatedSprite || root.selectedDex.sprite || ""
                                fillMode: Image.PreserveAspectFit
                                smooth: false
                                playing: visible && root.currentPage === 1
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: (root.selectedDex.showShiny ? "✨ " : "") +
                                          (root.selectedDex.name || "") + "  " +
                                          (root.selectedDex.number || "")
                                    color: root.textColor
                                    font.pixelSize: 19
                                    font.weight: Font.DemiBold
                                    Layout.fillWidth: true
                                }
                                AppButton {
                                    visible: !!root.selectedDex.hasShiny
                                    text: root.selectedDex.showShiny ? "Normal" : "Shiny"
                                    onClicked: appModel.toggleDexVariant(root.selectedDex.speciesId)
                                }
                            }
                            Text {
                                text: appModel.strings[root.selectedDex.rarity] || ""
                                color: root.mutedColor
                                font.pixelSize: 13
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 5
                                AppButton {
                                    objectName: "dexRepresentativeButton"
                                    Layout.fillWidth: true
                                    highlighted: !!root.selectedDex.representative
                                    text: root.selectedDex.representative
                                        ? (root.selectedDex.followingCurrent
                                            ? appModel.strings.following_current
                                            : appModel.strings.representative_selected)
                                        : appModel.strings.set_representative
                                    accessibleName: text
                                    onClicked: {
                                        if (!root.selectedDex.representative)
                                            appModel.chooseDexRepresentative(
                                                root.selectedDex.speciesId,
                                                !!root.selectedDex.showShiny
                                            )
                                    }
                                }
                                AppButton {
                                    objectName: "followCurrentRepresentativeButton"
                                    visible: !appModel.representativeFollowsCurrent
                                    Layout.fillWidth: true
                                    text: appModel.strings.follow_companion
                                    onClicked: appModel.followCurrentRepresentative()
                                }
                            }
                        }
                    }
                    RowLayout {
                        objectName: "dexDetailNavigation"
                        visible: root.collectionMode === "dex" && root.selectedDexIndex >= 0
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        AppButton {
                            text: appModel.strings.previous
                            enabled: root.selectedDexIndex > 0
                            onClicked: {
                                root.selectedDexIndex--
                                collectionPage.contentItem.contentY = 0
                            }
                        }
                        Item { Layout.fillWidth: true }
                        AppButton {
                            text: appModel.strings.next
                            enabled: root.selectedDexIndex < appModel.dexBrowseEntries.length - 1
                            onClicked: {
                                root.selectedDexIndex++
                                collectionPage.contentItem.contentY = 0
                            }
                        }
                    }
                    Text { visible: root.collectionMode === "catches" && appModel.catches.length === 0; Layout.leftMargin: 14; text: appModel.strings.empty_catches; color: root.mutedColor; font.pixelSize: 12 }
                    Repeater {
                        model: root.collectionMode === "catches" ? appModel.catches : []
                        Panel {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.leftMargin: 14
                            Layout.rightMargin: 14
                            Layout.preferredHeight: 230
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 5
                                Item {
                                    objectName: "catchHeader"
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 32
                                    Column {
                                        anchors.left: parent.left
                                        anchors.top: parent.top
                                        spacing: 2
                                        Text { text: (modelData.shiny ? "✨ " : "") + modelData.name + "  " + modelData.number; color: root.textColor; font.pixelSize: 14; font.weight: Font.Medium }
                                        Text { text: modelData.meta; color: root.mutedColor; font.pixelSize: 10 }
                                    }
                                    Text {
                                        objectName: "raisingBadge"
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        visible: modelData.current
                                        text: appModel.strings.raising
                                        color: root.accentColor
                                        font.pixelSize: 10
                                        font.weight: Font.Medium
                                    }
                                }
                                Text {
                                    text: modelData.description
                                    color: root.mutedColor
                                    font.pixelSize: 13
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 3
                                    Repeater {
                                        model: modelData.stages
                                        RowLayout {
                                            required property var modelData
                                            required property int index
                                            Layout.fillWidth: true
                                            spacing: 3
                                            Text { objectName: "evolutionArrow"; visible: index > 0; text: "→"; color: root.accentColor; font.pixelSize: 18; font.weight: Font.Bold }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 1
                                                Image { source: modelData.sprite; opacity: modelData.owned ? 1 : 0.3; Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: 104; Layout.preferredHeight: 104; fillMode: Image.PreserveAspectFit; smooth: false }
                                                Text { text: modelData.name; color: modelData.owned ? root.textColor : root.mutedColor; font.pixelSize: 11; elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                                                Text { text: modelData.status; color: modelData.current ? root.accentColor : root.mutedColor; font.pixelSize: 10; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Item { Layout.preferredHeight: 10 }
                }
            }

            PageScroll {
                id: bagPage
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: bagPage.availableWidth
                    spacing: 10
                    Item { Layout.preferredHeight: 4 }
                    GridLayout {
                        id: bagGrid
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        columns: width > 740 ? 2 : 1
                        columnSpacing: 8
                        rowSpacing: 8
                        BagItemCard {
                            objectName: "rareCandyBagCard"
                            visible: appModel.rareCandyCount > 0
                            itemKind: "rare_candy"
                            itemName: appModel.strings.rare_candy
                            icon: "🍬"
                            count: appModel.rareCandyCount
                            description: root.format(appModel.strings.bag_candy_description, {amount: appModel.rareCandyXp})
                            effectHint: root.format(appModel.strings.bag_candy_effect, {amount: appModel.rareCandyXp})
                            unavailableReason: appModel.strings.bag_use_after_hatch
                            canUse: appModel.hasActiveCompanion
                        }
                        BagItemCard {
                            objectName: "mintBagCard"
                            visible: appModel.mintCount > 0
                            itemKind: "mint"
                            itemName: appModel.strings.mint
                            icon: "🌿"
                            count: appModel.mintCount
                            description: appModel.strings.bag_mint_description
                            effectHint: appModel.strings.bag_mint_effect
                            unavailableReason: appModel.strings.bag_use_after_hatch
                            canUse: appModel.hasActiveCompanion
                        }
                        BagItemCard {
                            objectName: "shinyCharmBagCard"
                            visible: appModel.shinyCharmActive
                            Layout.columnSpan: bagGrid.columns
                            itemKind: "shiny_charm"
                            itemName: appModel.strings.shiny_charm
                            icon: "✨"
                            description: appModel.strings.bag_charm_description
                            effectHint: appModel.strings.bag_charm_effect
                            passive: true
                        }
                    }
                    Panel {
                        visible: appModel.rareCandyCount === 0 && appModel.mintCount === 0 && !appModel.shinyCharmActive
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        Layout.preferredHeight: 130
                        Text {
                            anchors.centerIn: parent
                            width: parent.width - 28
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            text: appModel.strings.bag_empty
                            color: root.mutedColor
                            font.pixelSize: 13
                            font.weight: Font.Medium
                        }
                    }
                }
            }

            PageScroll {
                id: shopPage
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: shopPage.availableWidth
                    spacing: 10
                    Item { Layout.preferredHeight: 4 }
                    GridLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        columns: width > 720 ? 3 : (width > 470 ? 2 : 1)
                        columnSpacing: 8
                        rowSpacing: 8
                        Repeater {
                            model: appModel.shopItems
                            Panel {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: 172
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 4
                                    Item {
                                        Layout.preferredWidth: 46
                                        Layout.preferredHeight: 46
                                        Text {
                                            visible: modelData.kind !== "egg"
                                            anchors.centerIn: parent
                                            text: modelData.icon
                                            font.pixelSize: 30
                                        }
                                        EggIcon {
                                            objectName: "shopEggIcon-" + modelData.key
                                            visible: modelData.kind === "egg"
                                            anchors.centerIn: parent
                                            width: 42
                                            height: 42
                                            tier: modelData.eggTier
                                        }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6
                                        Text { text: modelData.title; color: root.textColor; font.pixelSize: 15; font.weight: Font.Medium; Layout.fillWidth: true }
                                        Rectangle {
                                            visible: modelData.kind === "egg" && modelData.key !== "normal"
                                            implicitHeight: 18
                                            implicitWidth: eggRarityLabel.implicitWidth + 12
                                            radius: 9
                                            color: modelData.key === "rare" ? "#7b4bc4" : "#2f7fca"
                                            Text {
                                                id: eggRarityLabel
                                                anchors.centerIn: parent
                                                text: (appModel.strings[modelData.key] || "").toUpperCase()
                                                color: "#ffffff"
                                                font.pixelSize: 9
                                                font.weight: Font.Bold
                                            }
                                        }
                                    }
                                    Text { text: modelData.subtitle; color: root.mutedColor; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                                    Item { Layout.fillHeight: true }
                                    AppButton {
                                        Layout.fillWidth: true
                                        text: modelData.owned ? appModel.strings.already_active : modelData.price + " " + appModel.strings.tokens
                                        accessibleName: root.format(appModel.strings.buy, {title: modelData.title, price: text})
                                        highlighted: modelData.enabled
                                        enabled: modelData.enabled
                                        onClicked: appModel.buy(modelData.kind, modelData.key)
                                    }
                                }
                            }
                        }
                    }
                    Item { Layout.preferredHeight: 10 }
                }
            }


            PageScroll {
                id: settingsPage
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: settingsPage.availableWidth
                    spacing: 9
                    Item { Layout.preferredHeight: 4 }
                    GridLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        columns: width > 760 ? 2 : 1
                        columnSpacing: 8
                        rowSpacing: 8

                        Panel {
                            objectName: "generalSettingsPanel"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 182
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 12; spacing: 8
                                Text { text: appModel.strings.general; color: root.textColor; font.pixelSize: 15; font.weight: Font.Medium }
                                RowLayout {
                                    Layout.fillWidth: true
                                    InfoLabel { text: appModel.strings.refresh_interval; helpText: appModel.strings.refresh_help; Layout.fillWidth: true }
                                    StyledComboBox {
                                        objectName: "refreshIntervalCombo"
                                        model: [1, 2, 5, 10, 15]
                                        activeFocusOnTab: true
                                        Accessible.name: appModel.strings.refresh_interval
                                        FocusFrame { }
                                        currentIndex: Math.max(0, model.indexOf(appModel.refreshMinutes))
                                        delegate: ItemDelegate {
                                            required property var modelData
                                            width: parent ? parent.width : 100
                                            contentItem: Text {
                                                text: root.format(appModel.strings.minutes, {count: modelData})
                                                color: root.textColor
                                                font.pixelSize: 12
                                                verticalAlignment: Text.AlignVCenter
                                            }
                                            background: Rectangle {
                                                color: parent.hovered || parent.highlighted ? root.accentSurface : root.panelColor
                                            }
                                        }
                                        contentItem: Text { text: root.format(appModel.strings.minutes, {count: parent.currentText}); color: root.textColor; verticalAlignment: Text.AlignVCenter; leftPadding: 8 }
                                        onActivated: appModel.setRefreshMinutes(model[currentIndex])
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    InfoLabel {
                                        text: appModel.strings.language
                                        helpText: appModel.strings.language_help
                                        Layout.fillWidth: true
                                    }
                                    StyledComboBox {
                                        id: languageCombo
                                        objectName: "languageCombo"
                                        activeFocusOnTab: true
                                        Accessible.name: appModel.strings.language
                                        FocusFrame { }
                                        model: appModel.languageOptions
                                        textRole: "label"
                                        currentIndex: ["en", "es", "gl"].indexOf(appModel.language)
                                        onActivated: appModel.setLanguage(model[currentIndex].key)
                                    }
                                }
                                ToggleRow { label: appModel.strings.start_windows; detail: appModel.strings.start_windows_help; checked: appModel.autostart; onChanged: value => appModel.setAutostart(value) }
                            }
                        }

                        Panel {
                            objectName: "desktopPetPanel"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 258
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 12; spacing: 7
                                Text { text: appModel.strings.desktop_pet; color: root.textColor; font.pixelSize: 15; font.weight: Font.Medium }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 3
                                    InfoLabel { text: appModel.strings.desktop_representative; helpText: appModel.strings.representative_help }
                                    StyledComboBox {
                                        id: representativeCombo
                                        objectName: "representativeCombo"
                                        Layout.fillWidth: true
                                        activeFocusOnTab: true
                                        Accessible.name: appModel.strings.desktop_representative
                                        Accessible.description: appModel.strings.representative_help
                                        ToolTip.visible: hovered || activeFocus
                                        ToolTip.delay: 550
                                        ToolTip.text: appModel.strings.representative_help
                                        FocusFrame { }
                                        model: appModel.collection
                                        textRole: "display"
                                        currentIndex: {
                                            for (let i = 0; i < model.length; ++i)
                                                if (model[i].selected) return i
                                            return 0
                                        }
                                        onActivated: appModel.chooseRepresentative(currentIndex)
                                    }
                                }
                                ToggleRow { label: appModel.strings.show_floating; detail: appModel.strings.show_floating_help; checked: appModel.petEnabled; onChanged: value => appModel.setPetEnabled(value) }
                                RowLayout {
                                    Layout.fillWidth: true
                                    InfoLabel { text: appModel.strings.size; helpText: appModel.strings.pet_size_help }
                                    Slider { objectName: "petSizeSlider"; Layout.fillWidth: true; from: 48; to: 192; stepSize: 8; value: appModel.petSize; enabled: appModel.petEnabled; activeFocusOnTab: true; Accessible.name: appModel.strings.pet_size; onMoved: appModel.setPetSize(value); FocusFrame { } }
                                    Text { text: appModel.petSize + " px"; color: root.mutedColor; font.pixelSize: 11 }
                                }
                                ToggleRow { label: appModel.strings.usage_bubbles; detail: appModel.strings.usage_bubbles_help; checked: appModel.petAlerts; onChanged: value => appModel.setPreference("petAlerts", value) }
                            }
                        }


                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 460
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 12; spacing: 7
                                Text { text: appModel.strings.limits_alerts; color: root.textColor; font.pixelSize: 15; font.weight: Font.Medium }
                                RowLayout {
                                    Layout.fillWidth: true
                                    InfoLabel { text: appModel.strings.show_quota; helpText: appModel.strings.quota_help; Layout.fillWidth: true }
                                    SegmentedControl {
                                        objectName: "limitDisplayControl"
                                        options: [{label: appModel.strings.used, value: "used"}, {label: appModel.strings.remaining, value: "remaining"}]
                                        currentValue: appModel.limitDisplayMode
                                        accessibleName: appModel.strings.quota_percentage
                                        onSelected: value => appModel.setPreference("limitDisplayMode", value)
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    InfoLabel { text: appModel.strings.reset_format; helpText: appModel.strings.reset_format_help; Layout.fillWidth: true }
                                    SegmentedControl {
                                        objectName: "limitTimeControl"
                                        options: [{label: appModel.strings.time, value: "remaining"}, {label: appModel.strings.date, value: "datetime"}]
                                        currentValue: appModel.limitTimeMode
                                        accessibleName: appModel.strings.reset_format
                                        onSelected: value => appModel.setPreference("limitTimeMode", value)
                                    }
                                }
                                ToggleRow { label: appModel.strings.forecast_timed; detail: appModel.strings.forecast_help; checked: appModel.forecastEnabled; onChanged: value => appModel.setPreference("forecastEnabled", value) }
                                ToggleRow { label: appModel.strings.limit_notifications; detail: appModel.strings.limit_notifications_help; checked: appModel.limitNotifications; onChanged: value => appModel.setPreference("limitNotifications", value) }
                                ToggleRow { label: appModel.strings.limit_reset_notifications; detail: appModel.strings.limit_reset_notifications_help; checked: appModel.limitResetNotifications; onChanged: value => appModel.setPreference("limitResetNotifications", value) }
                                ToggleRow { label: appModel.strings.banked_reset_notifications; detail: appModel.strings.banked_reset_notifications_help; checked: appModel.bankedResetNotifications; onChanged: value => appModel.setPreference("bankedResetNotifications", value) }
                                ToggleRow { label: appModel.strings.pokemon_notifications; detail: appModel.strings.pokemon_notifications_help; checked: appModel.companionNotifications; onChanged: value => appModel.setPreference("companionNotifications", value) }
                                RowLayout {
                                    Layout.fillWidth: true
                                    InfoLabel { text: appModel.strings.warning; helpText: appModel.strings.warning_help; Layout.fillWidth: true }
                                    StyledSpinBox { objectName: "warningThresholdSpin"; from: 50; to: 95; stepSize: 5; value: appModel.warningThreshold; editable: false; activeFocusOnTab: true; Accessible.name: appModel.strings.warning_threshold; textFromValue: value => value + "%"; valueFromText: text => parseInt(text); onValueModified: appModel.setPreference("warningThreshold", value); contentItem.activeFocusOnTab: false; FocusFrame { } }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    InfoLabel { text: appModel.strings.critical; helpText: appModel.strings.critical_help; Layout.fillWidth: true }
                                    StyledSpinBox { objectName: "criticalThresholdSpin"; from: 80; to: 100; stepSize: 5; value: appModel.criticalThreshold; editable: false; activeFocusOnTab: true; Accessible.name: appModel.strings.critical_threshold; textFromValue: value => value + "%"; valueFromText: text => parseInt(text); onValueModified: appModel.setPreference("criticalThreshold", value); contentItem.activeFocusOnTab: false; FocusFrame { } }
                                }
                            }
                        }

                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 260
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 12; spacing: 7
                                Text { text: appModel.strings.appearance_data; color: root.textColor; font.pixelSize: 15; font.weight: Font.Medium }
                                RowLayout {
                                    Layout.fillWidth: true
                                    InfoLabel { text: appModel.strings.theme; helpText: appModel.strings.theme_help; Layout.fillWidth: true }
                                    StyledComboBox {
                                        objectName: "themeCombo"
                                        activeFocusOnTab: true
                                        Accessible.name: appModel.strings.interface_theme
                                        FocusFrame { }
                                        model: [appModel.strings.theme_system, appModel.strings.theme_light, appModel.strings.theme_dark]
                                        currentIndex: appModel.theme === "light" ? 1 : (appModel.theme === "dark" ? 2 : 0)
                                        onActivated: appModel.setPreference("theme", ["system", "light", "dark"][currentIndex])
                                    }
                                }
                                ToggleRow { label: appModel.strings.tray_today; detail: appModel.strings.tray_today_help; checked: appModel.trayShowTokens; onChanged: value => appModel.setPreference("trayShowTokens", value) }
                                ToggleRow { label: appModel.strings.tray_cost; detail: appModel.strings.tray_cost_help; checked: appModel.trayShowCost; onChanged: value => appModel.setPreference("trayShowCost", value) }
                                ToggleRow { objectName: "trayLimitToggle"; label: appModel.strings.tray_limit; detail: appModel.strings.tray_limit_help; checked: appModel.trayShowLimit; onChanged: value => appModel.setPreference("trayShowLimit", value) }
                                RowLayout {
                                    Layout.fillWidth: true
                                    AppButton { text: appModel.strings.export_backup; ToolTip.visible: hovered; ToolTip.text: appModel.strings.backup_help; onClicked: appModel.requestExport() }
                                    AppButton { text: appModel.strings.import_backup; ToolTip.visible: hovered; ToolTip.text: appModel.strings.backup_help; onClicked: appModel.requestImport() }
                                }
                            }
                        }
                    }
                    Item { Layout.preferredHeight: 10 }
                }
            }
        }
    }

    ResizeHandle { objectName: "leftResizeHandle"; anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom; width: 8; resizeEdges: Qt.LeftEdge; cursorShape: Qt.SizeHorCursor }
    ResizeHandle { objectName: "rightResizeHandle"; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom; width: 8; resizeEdges: Qt.RightEdge; cursorShape: Qt.SizeHorCursor }
    ResizeHandle { objectName: "topResizeHandle"; anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; height: 8; resizeEdges: Qt.TopEdge; cursorShape: Qt.SizeVerCursor }
    ResizeHandle { objectName: "bottomResizeHandle"; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right; height: 8; resizeEdges: Qt.BottomEdge; cursorShape: Qt.SizeVerCursor }
    ResizeHandle { objectName: "topLeftResizeHandle"; anchors.left: parent.left; anchors.top: parent.top; width: 12; height: 12; resizeEdges: Qt.TopEdge | Qt.LeftEdge; cursorShape: Qt.SizeFDiagCursor }
    ResizeHandle { objectName: "topRightResizeHandle"; anchors.right: parent.right; anchors.top: parent.top; width: 12; height: 12; resizeEdges: Qt.TopEdge | Qt.RightEdge; cursorShape: Qt.SizeBDiagCursor }
    ResizeHandle { objectName: "bottomLeftResizeHandle"; anchors.left: parent.left; anchors.bottom: parent.bottom; width: 12; height: 12; resizeEdges: Qt.BottomEdge | Qt.LeftEdge; cursorShape: Qt.SizeBDiagCursor }
    ResizeHandle { objectName: "bottomRightResizeHandle"; anchors.right: parent.right; anchors.bottom: parent.bottom; width: 12; height: 12; resizeEdges: Qt.BottomEdge | Qt.RightEdge; cursorShape: Qt.SizeFDiagCursor }

    Rectangle {
        visible: appModel.feedbackText.length > 0
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 12
        width: Math.min(parent.width - 30, feedbackText.implicitWidth + 30)
        height: 38
        radius: 9
        color: root.darkMode ? "#dce7ff" : "#21365e"
        z: 30
        Text { id: feedbackText; anchors.centerIn: parent; text: appModel.feedbackText; color: root.darkMode ? "#17233c" : "#ffffff"; font.pixelSize: 12 }
    }

    Rectangle {
        visible: appModel.toastText.length > 0
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.topMargin: 10
        width: Math.min(parent.width - 30, toastText.implicitWidth + 40)
        height: 42
        radius: 10
        color: appModel.toastShiny ? (root.darkMode ? "#4b3e17" : "#fff2bd") : root.panelColor
        border.color: appModel.toastShiny ? root.warningColor : root.borderColor
        z: 40
        Text { id: toastText; anchors.centerIn: parent; text: (appModel.toastShiny ? "✨  " : "") + appModel.toastText; color: root.textColor; font.pixelSize: 13; font.weight: Font.Medium }
    }
}
