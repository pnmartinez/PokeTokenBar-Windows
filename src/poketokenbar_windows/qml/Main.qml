import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Layouts

Rectangle {
    id: root
    width: 560
    height: 740
    color: appModel.darkMode ? "#0d121b" : "#f4f7fb"

    property int currentPage: 0
    property string collectionMode: "dex"
    readonly property bool darkMode: appModel.darkMode
    property color textColor: appModel.darkMode ? "#edf2ff" : "#172033"
    property color mutedColor: appModel.darkMode ? "#9ba9bf" : "#667289"
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
        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: "#ef5261"
            border.color: root.textColor
            border.width: 2
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                height: 4
                color: root.textColor
            }
            Rectangle {
                anchors.centerIn: parent
                width: 9
                height: 9
                radius: 5
                color: root.panelColor
                border.color: root.textColor
                border.width: 2
            }
        }
    }

    component Panel: Rectangle {
        color: root.panelColor
        radius: 11
        border.color: root.borderColor
        border.width: 1
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
            font.pixelSize: 12
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

    component NavButton: Button {
        id: nav
        required property int pageIndex
        checkable: true
        checked: root.currentPage === pageIndex
        activeFocusOnTab: true
        Accessible.name: nav.text
        Accessible.role: Accessible.PageTab
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
        contentItem: Text {
            text: nav.text
            color: nav.checked ? root.textColor : root.mutedColor
            font.pixelSize: root.width < 600 ? 10 : 12
            font.weight: nav.checked ? Font.Medium : Font.Normal
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }

    component PageHeading: RowLayout {
        required property string title
        required property string subtitle
        Layout.fillWidth: true
        spacing: 10
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Text {
                text: title
                color: root.textColor
                font.pixelSize: 21
                font.weight: Font.Medium
            }
            Text {
                text: subtitle
                color: root.mutedColor
                font.pixelSize: 11
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
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
        Layout.preferredHeight: 52
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 9
            spacing: 1
            Text { text: label; color: root.mutedColor; font.pixelSize: 10 }
            Text { text: value; color: root.textColor; font.pixelSize: 16; font.weight: Font.DemiBold }
        }
    }

    component WalletBadge: Rectangle {
        implicitWidth: 126
        implicitHeight: 46
        radius: 10
        color: root.accentSurface
        border.color: root.accentColor
        RowLayout {
            anchors.fill: parent
            anchors.margins: 9
            spacing: 7
            Text { text: "◉"; color: root.accentColor; font.pixelSize: 15 }
            ColumnLayout {
                spacing: 0
                Text { text: appModel.strings.wallet; color: root.mutedColor; font.pixelSize: 9 }
                Text { text: appModel.wallet; color: root.textColor; font.pixelSize: 14; font.weight: Font.DemiBold }
            }
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
            Text { text: toggleRow.label; color: root.textColor; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { visible: toggleRow.detail.length > 0; text: toggleRow.detail; color: root.mutedColor; font.pixelSize: 10; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
        Switch {
            id: toggle
            activeFocusOnTab: true
            Accessible.name: toggleRow.label
            Accessible.description: toggleRow.detail
            FocusFrame { }
            onToggled: toggleRow.changed(checked)
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
                        font.pixelSize: 10
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
            Layout.fillWidth: true
            Layout.preferredHeight: 82
            color: root.panelColor
            border.color: root.borderColor
            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                spacing: 0
                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    spacing: 8
                    PokeBall { Layout.preferredWidth: 24; Layout.preferredHeight: 24 }
                    Text {
                        text: "PokeTokenBar"
                        color: root.textColor
                        font.pixelSize: 15
                        font.weight: Font.DemiBold
                    }
                    Item { Layout.fillWidth: true }
                    Rectangle { width: 7; height: 7; radius: 4; color: appModel.loading ? root.warningColor : root.successColor }
                    Text {
                        text: appModel.statusText
                        color: root.mutedColor
                        font.pixelSize: 9
                        elide: Text.ElideRight
                        Layout.maximumWidth: 150
                    }
                }
                RowLayout {
                    objectName: "topNavigation"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    spacing: 2
                    NavButton { pageIndex: 0; text: appModel.strings.nav_home; Layout.fillWidth: true }
                    NavButton { pageIndex: 1; text: appModel.strings.nav_collection; Layout.fillWidth: true }
                    NavButton { pageIndex: 2; text: appModel.strings.nav_bag; Layout.fillWidth: true }
                    NavButton { pageIndex: 3; text: appModel.strings.nav_shop; Layout.fillWidth: true }
                    NavButton { pageIndex: 4; text: appModel.strings.nav_settings; Layout.fillWidth: true }
                }
            }
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

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Text { text: "PokeTokenBar"; color: root.textColor; font.pixelSize: 20; font.weight: Font.Medium }
                            Text { text: appModel.strings.home_description; color: root.mutedColor; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                        AppButton {
                            text: appModel.strings.refresh
                            accessibleName: appModel.strings.refresh
                            highlighted: true
                            enabled: appModel.refreshEnabled
                            onClicked: appModel.requestRefresh()
                        }
                    }

                    Panel {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 132
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 11
                            spacing: 12
                            Rectangle {
                                Layout.preferredWidth: 104
                                Layout.fillHeight: true
                                radius: 12
                                color: root.accentSurface
                                Image {
                                    anchors.fill: parent
                                    anchors.margins: 5
                                    source: appModel.spriteUrl
                                    fillMode: Image.PreserveAspectFit
                                    smooth: false
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 3
                                Text { text: appModel.strings.current_companion; color: root.mutedColor; font.pixelSize: 9; font.letterSpacing: 1 }
                                Text { text: appModel.companionName; color: root.textColor; font.pixelSize: 20; font.weight: Font.Medium; elide: Text.ElideRight; Layout.fillWidth: true }
                                Text { text: appModel.companionSubtitle; color: root.mutedColor; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                                Text { text: appModel.companionEvolutionText; color: root.mutedColor; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                                Item { Layout.fillHeight: true }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: appModel.companionProgressText; color: root.textColor; font.pixelSize: 11; Layout.fillWidth: true }
                                    Text { text: appModel.companionLevelText; color: root.textColor; font.pixelSize: 14; font.weight: Font.Bold }
                                }
                                ModernProgress { Layout.fillWidth: true; value: appModel.companionProgress }
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
                        id: providersPanel
                        objectName: "providersPanel"
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(122, Math.max(52, 30 + Math.max(1, appModel.providers.length) * 28))
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 4
                            Text { text: appModel.strings.providers; color: root.textColor; font.pixelSize: 12; font.weight: Font.DemiBold }
                            ListView {
                                id: providersList
                                objectName: "providersList"
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
                                        Text { text: modelData.name; color: modelData.error ? root.dangerColor : root.textColor; font.pixelSize: 10; font.weight: Font.Medium; Layout.preferredWidth: 74; elide: Text.ElideRight }
                                        Text { text: modelData.today + " " + appModel.strings.today_short; color: root.textColor; font.pixelSize: 9 }
                                        Text { text: modelData.week + " " + appModel.strings.week_short; color: root.mutedColor; font.pixelSize: 9 }
                                        Item { Layout.fillWidth: true }
                                        Text { text: modelData.cost; color: root.textColor; font.pixelSize: 9; font.weight: Font.Medium }
                                    }
                                }
                            }
                            Text { visible: appModel.providers.length === 0; text: appModel.strings.no_provider_data; color: root.mutedColor; font.pixelSize: 10 }
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
                            Text { text: appModel.strings.official_limits; color: root.textColor; font.pixelSize: 12; font.weight: Font.DemiBold }
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
                                            Text {
                                                text: modelData.kind === "credit"
                                                    ? modelData.provider + " · " + modelData.label
                                                    : modelData.provider + (modelData.plan.length ? " · " + modelData.plan : "") + " · " + modelData.label
                                                color: modelData.urgency === "critical" ? root.dangerColor : (modelData.urgency === "warning" ? root.warningColor : root.textColor)
                                                font.pixelSize: 10
                                                font.weight: modelData.kind === "credit" ? Font.DemiBold : Font.Medium
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                            }
                                            Text { visible: modelData.kind !== "credit"; text: modelData.percentText; color: root.textColor; font.pixelSize: 10; font.weight: Font.DemiBold }
                                        }
                                        RowLayout {
                                            visible: modelData.kind === "window"
                                            Layout.fillWidth: true
                                            Text { text: modelData.reset; color: root.mutedColor; font.pixelSize: 9; Layout.fillWidth: true }
                                            Text { visible: modelData.forecast.length > 0; text: appModel.strings.forecast + ": " + modelData.forecast; color: root.mutedColor; font.pixelSize: 9; elide: Text.ElideRight; Layout.maximumWidth: 230 }
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
                            Text { visible: appModel.limits.length === 0; text: appModel.strings.no_limit_data; color: root.mutedColor; font.pixelSize: 10 }
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
                    PageHeading {
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        title: appModel.strings.nav_collection
                        subtitle: appModel.strings.collection_description
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        SegmentedControl {
                            objectName: "collectionModeControl"
                            options: [{label: appModel.strings.pokedex, value: "dex"}, {label: appModel.strings.catch_log, value: "catches"}]
                            currentValue: root.collectionMode
                            accessibleName: appModel.strings.collection_view
                            onSelected: value => root.collectionMode = value
                        }
                        Item { Layout.fillWidth: true }
                        Text {
                            visible: root.collectionMode === "dex"
                            text: root.format(appModel.strings.page, {page: appModel.dexPage, count: appModel.dexPageCount})
                            color: root.mutedColor
                            font.pixelSize: 10
                        }
                    }
                    Flow {
                        visible: root.collectionMode === "dex"
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        spacing: 6
                        Repeater {
                            model: appModel.dexFilters
                            AppButton {
                                required property var modelData
                                text: modelData.label + "  " + modelData.count
                                accessibleName: root.format(appModel.strings.filter_by, {label: modelData.label})
                                highlighted: appModel.dexFilter === modelData.key
                                onClicked: appModel.setDexFilter(modelData.key)
                            }
                        }
                    }
                    Text {
                        visible: root.collectionMode === "dex"
                        Layout.leftMargin: 14
                        text: appModel.dexSummary
                        color: root.mutedColor
                        font.pixelSize: 10
                    }
                    GridLayout {
                        visible: root.collectionMode === "dex"
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        columns: width >= 720 ? 4 : (width >= 470 ? 3 : 2)
                        columnSpacing: 7
                        rowSpacing: 7
                        Repeater {
                            model: appModel.dexEntries
                            Panel {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: 132
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 8
                                    spacing: 2
                                    Image { source: modelData.sprite; Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: 66; Layout.preferredHeight: 66; fillMode: Image.PreserveAspectFit; smooth: false }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: modelData.number; color: root.mutedColor; font.pixelSize: 9 }
                                        Item { Layout.fillWidth: true }
                                        Text { visible: modelData.showShiny; text: "✨"; font.pixelSize: 10 }
                                    }
                                    Text { text: modelData.name; color: root.textColor; font.pixelSize: 11; font.weight: Font.Medium; elide: Text.ElideRight; Layout.fillWidth: true }
                                    AppButton {
                                        Layout.fillWidth: true
                                        visible: modelData.hasShiny
                                        text: modelData.showShiny ? "Normal" : "Shiny"
                                        accessibleName: root.format(modelData.showShiny ? appModel.strings.view_normal : appModel.strings.view_shiny, {name: modelData.name})
                                        onClicked: appModel.toggleDexVariant(modelData.speciesId)
                                    }
                                }
                            }
                        }
                    }
                    Text { visible: root.collectionMode === "dex" && appModel.dexEntries.length === 0; Layout.leftMargin: 14; text: appModel.strings.empty_pokedex; color: root.mutedColor; font.pixelSize: 11 }
                    RowLayout {
                        visible: root.collectionMode === "dex"
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        AppButton { text: appModel.strings.previous; enabled: appModel.dexPage > 1; onClicked: appModel.moveDexPage(-1) }
                        Item { Layout.fillWidth: true }
                        AppButton { text: appModel.strings.next; enabled: appModel.dexPage < appModel.dexPageCount; onClicked: appModel.moveDexPage(1) }
                    }
                    Text { visible: root.collectionMode === "catches" && appModel.catches.length === 0; Layout.leftMargin: 14; text: appModel.strings.empty_catches; color: root.mutedColor; font.pixelSize: 11 }
                    Repeater {
                        model: root.collectionMode === "catches" ? appModel.catches : []
                        Panel {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.leftMargin: 14
                            Layout.rightMargin: 14
                            Layout.preferredHeight: 154
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 5
                                RowLayout {
                                    Layout.fillWidth: true
                                    Image { source: modelData.sprite; Layout.preferredWidth: 48; Layout.preferredHeight: 48; fillMode: Image.PreserveAspectFit; smooth: false }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Text { text: (modelData.shiny ? "✨ " : "") + modelData.name + "  " + modelData.number; color: root.textColor; font.pixelSize: 13; font.weight: Font.Medium }
                                        Text { text: modelData.meta; color: root.mutedColor; font.pixelSize: 9 }
                                    }
                                    Text { visible: modelData.current; text: appModel.strings.raising; color: root.accentColor; font.pixelSize: 9; font.weight: Font.Medium }
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
                                                Image { source: modelData.sprite; opacity: modelData.owned ? 1 : 0.3; Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: 38; Layout.preferredHeight: 38; fillMode: Image.PreserveAspectFit; smooth: false }
                                                Text { text: modelData.name; color: modelData.owned ? root.textColor : root.mutedColor; font.pixelSize: 8; elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                                                Text { text: modelData.status; color: modelData.current ? root.accentColor : root.mutedColor; font.pixelSize: 8; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
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
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        PageHeading { title: appModel.strings.nav_bag; subtitle: appModel.strings.bag_description; Layout.fillWidth: true }
                        WalletBadge { }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        columns: width > 560 ? 2 : 1
                        columnSpacing: 8
                        rowSpacing: 8
                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 126
                            RowLayout {
                                anchors.fill: parent; anchors.margins: 12; spacing: 12
                                Text { text: "🍬"; font.pixelSize: 36 }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Text { text: appModel.strings.rare_candy; color: root.textColor; font.pixelSize: 15; font.weight: Font.Medium }
                                    Text { text: root.format(appModel.strings.available_count, {count: appModel.rareCandyCount}); color: root.mutedColor; font.pixelSize: 11 }
                                    AppButton { text: appModel.strings.use_on_companion; enabled: appModel.rareCandyCount > 0; onClicked: appModel.useItem("rare_candy") }
                                }
                            }
                        }
                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 126
                            RowLayout {
                                anchors.fill: parent; anchors.margins: 12; spacing: 12
                                Text { text: "🌿"; font.pixelSize: 36 }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Text { text: appModel.strings.mint; color: root.textColor; font.pixelSize: 15; font.weight: Font.Medium }
                                    Text { text: root.format(appModel.strings.available_count, {count: appModel.mintCount}); color: root.mutedColor; font.pixelSize: 11 }
                                    AppButton { text: appModel.strings.change_nature; enabled: appModel.mintCount > 0; onClicked: appModel.useItem("mint") }
                                }
                            }
                        }
                        Panel {
                            Layout.fillWidth: true
                            Layout.columnSpan: width > 560 ? 2 : 1
                            Layout.preferredHeight: 90
                            RowLayout {
                                anchors.fill: parent; anchors.margins: 12; spacing: 12
                                Text { text: "✨"; font.pixelSize: 30 }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Text { text: appModel.strings.shiny_charm; color: root.textColor; font.pixelSize: 14; font.weight: Font.Medium }
                                    Text { text: appModel.shinyCharmActive ? appModel.strings.charm_active : appModel.strings.charm_inactive; color: appModel.shinyCharmActive ? root.successColor : root.mutedColor; font.pixelSize: 10; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                }
                            }
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
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        PageHeading { title: appModel.strings.nav_shop; subtitle: appModel.strings.shop_description; Layout.fillWidth: true }
                        WalletBadge { }
                    }
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
                                    Text { text: modelData.icon; font.pixelSize: 30 }
                                    Text { text: modelData.title; color: root.textColor; font.pixelSize: 14; font.weight: Font.Medium }
                                    Text { text: modelData.subtitle; color: root.mutedColor; font.pixelSize: 10; Layout.fillWidth: true; wrapMode: Text.WordWrap }
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
                    PageHeading {
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        title: appModel.strings.nav_settings
                        subtitle: appModel.strings.settings_description
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        columns: width > 760 ? 2 : 1
                        columnSpacing: 8
                        rowSpacing: 8

                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 286
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 12; spacing: 8
                                Text { text: appModel.strings.general; color: root.textColor; font.pixelSize: 14; font.weight: Font.Medium }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: appModel.strings.refresh_interval; color: root.textColor; font.pixelSize: 11; Layout.fillWidth: true }
                                    ComboBox {
                                        objectName: "refreshIntervalCombo"
                                        model: [1, 2, 5, 10, 15]
                                        activeFocusOnTab: true
                                        Accessible.name: appModel.strings.refresh_interval
                                        FocusFrame { }
                                        currentIndex: Math.max(0, model.indexOf(appModel.refreshMinutes))
                                        delegate: ItemDelegate { required property var modelData; width: parent ? parent.width : 100; text: root.format(appModel.strings.minutes, {count: modelData}) }
                                        contentItem: Text { text: root.format(appModel.strings.minutes, {count: parent.currentText}); color: root.textColor; verticalAlignment: Text.AlignVCenter; leftPadding: 8 }
                                        onActivated: appModel.setRefreshMinutes(model[currentIndex])
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Text { text: appModel.strings.language; color: root.textColor; font.pixelSize: 11 }
                                        Text { text: appModel.strings.language_help; color: root.mutedColor; font.pixelSize: 9; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    }
                                    ComboBox {
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
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 3
                                    Text { text: appModel.strings.desktop_representative; color: root.textColor; font.pixelSize: 11 }
                                    Text { text: appModel.strings.representative_help; color: root.mutedColor; font.pixelSize: 9; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    ComboBox {
                                        id: representativeCombo
                                        objectName: "representativeCombo"
                                        Layout.fillWidth: true
                                        activeFocusOnTab: true
                                        Accessible.name: appModel.strings.desktop_representative
                                        Accessible.description: appModel.strings.representative_help
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
                                ToggleRow { label: appModel.strings.start_windows; checked: appModel.autostart; onChanged: value => appModel.setAutostart(value) }
                            }
                        }

                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 178
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 12; spacing: 7
                                Text { text: appModel.strings.desktop_pet; color: root.textColor; font.pixelSize: 14; font.weight: Font.Medium }
                                ToggleRow { label: appModel.strings.show_floating; checked: appModel.petEnabled; onChanged: value => appModel.setPetEnabled(value) }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: appModel.strings.size; color: root.textColor; font.pixelSize: 11 }
                                    Slider { objectName: "petSizeSlider"; Layout.fillWidth: true; from: 48; to: 192; stepSize: 8; value: appModel.petSize; enabled: appModel.petEnabled; activeFocusOnTab: true; Accessible.name: appModel.strings.pet_size; onMoved: appModel.setPetSize(value); FocusFrame { } }
                                    Text { text: appModel.petSize + " px"; color: root.mutedColor; font.pixelSize: 10 }
                                }
                                ToggleRow { label: appModel.strings.usage_bubbles; checked: appModel.petAlerts; onChanged: value => appModel.setPreference("petAlerts", value) }
                            }
                        }


                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 374
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 12; spacing: 7
                                Text { text: appModel.strings.limits_alerts; color: root.textColor; font.pixelSize: 14; font.weight: Font.Medium }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: appModel.strings.show_quota; color: root.textColor; font.pixelSize: 11; Layout.fillWidth: true }
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
                                    Text { text: appModel.strings.reset_format; color: root.textColor; font.pixelSize: 11; Layout.fillWidth: true }
                                    SegmentedControl {
                                        objectName: "limitTimeControl"
                                        options: [{label: appModel.strings.time, value: "remaining"}, {label: appModel.strings.date, value: "datetime"}]
                                        currentValue: appModel.limitTimeMode
                                        accessibleName: appModel.strings.reset_format
                                        onSelected: value => appModel.setPreference("limitTimeMode", value)
                                    }
                                }
                                ToggleRow { label: appModel.strings.forecast_timed; checked: appModel.forecastEnabled; onChanged: value => appModel.setPreference("forecastEnabled", value) }
                                ToggleRow { label: appModel.strings.limit_notifications; checked: appModel.limitNotifications; onChanged: value => appModel.setPreference("limitNotifications", value) }
                                ToggleRow { label: appModel.strings.pokemon_notifications; checked: appModel.companionNotifications; onChanged: value => appModel.setPreference("companionNotifications", value) }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: appModel.strings.warning; color: root.textColor; font.pixelSize: 11; Layout.fillWidth: true }
                                    SpinBox { objectName: "warningThresholdSpin"; from: 50; to: 95; stepSize: 5; value: appModel.warningThreshold; editable: false; activeFocusOnTab: true; Accessible.name: appModel.strings.warning_threshold; textFromValue: value => value + "%"; valueFromText: text => parseInt(text); onValueModified: appModel.setPreference("warningThreshold", value); contentItem.activeFocusOnTab: false; FocusFrame { } }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: appModel.strings.critical; color: root.textColor; font.pixelSize: 11; Layout.fillWidth: true }
                                    SpinBox { objectName: "criticalThresholdSpin"; from: 80; to: 100; stepSize: 5; value: appModel.criticalThreshold; editable: false; activeFocusOnTab: true; Accessible.name: appModel.strings.critical_threshold; textFromValue: value => value + "%"; valueFromText: text => parseInt(text); onValueModified: appModel.setPreference("criticalThreshold", value); contentItem.activeFocusOnTab: false; FocusFrame { } }
                                }
                            }
                        }

                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 260
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 12; spacing: 7
                                Text { text: appModel.strings.appearance_data; color: root.textColor; font.pixelSize: 14; font.weight: Font.Medium }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: appModel.strings.theme; color: root.textColor; font.pixelSize: 11; Layout.fillWidth: true }
                                    ComboBox {
                                        objectName: "themeCombo"
                                        activeFocusOnTab: true
                                        Accessible.name: appModel.strings.interface_theme
                                        FocusFrame { }
                                        model: [appModel.strings.theme_system, appModel.strings.theme_light, appModel.strings.theme_dark]
                                        currentIndex: appModel.theme === "light" ? 1 : (appModel.theme === "dark" ? 2 : 0)
                                        onActivated: appModel.setPreference("theme", ["system", "light", "dark"][currentIndex])
                                    }
                                }
                                ToggleRow { label: appModel.strings.tray_today; checked: appModel.trayShowTokens; onChanged: value => appModel.setPreference("trayShowTokens", value) }
                                ToggleRow { label: appModel.strings.tray_cost; checked: appModel.trayShowCost; onChanged: value => appModel.setPreference("trayShowCost", value) }
                                ToggleRow { objectName: "trayLimitToggle"; label: appModel.strings.tray_limit; checked: appModel.trayShowLimit; onChanged: value => appModel.setPreference("trayShowLimit", value) }
                                RowLayout {
                                    Layout.fillWidth: true
                                    AppButton { text: appModel.strings.export_backup; onClicked: appModel.requestExport() }
                                    AppButton { text: appModel.strings.import_backup; onClicked: appModel.requestImport() }
                                }
                            }
                        }
                    }
                    Item { Layout.preferredHeight: 10 }
                }
            }
        }
    }

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
        Text { id: feedbackText; anchors.centerIn: parent; text: appModel.feedbackText; color: root.darkMode ? "#17233c" : "#ffffff"; font.pixelSize: 11 }
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
        Text { id: toastText; anchors.centerIn: parent; text: (appModel.toastShiny ? "✨  " : "") + appModel.toastText; color: root.textColor; font.pixelSize: 12; font.weight: Font.Medium }
    }
}
