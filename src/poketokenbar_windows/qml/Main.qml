import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Rectangle {
    id: root
    width: 1080
    height: 720
    color: appModel.darkMode ? "#0d121b" : "#f4f7fb"

    property int currentPage: 0
    property color textColor: appModel.darkMode ? "#edf2ff" : "#172033"
    property color mutedColor: appModel.darkMode ? "#9ba9bf" : "#667289"
    property color panelColor: appModel.darkMode ? "#18212e" : "#ffffff"
    property color panelAltColor: appModel.darkMode ? "#202b3b" : "#edf3ff"
    property color borderColor: appModel.darkMode ? "#2b394e" : "#dce3ed"
    property color sidebarColor: appModel.darkMode ? "#141b27" : "#eaf0f9"
    property color accentColor: appModel.darkMode ? "#8facff" : "#315da8"
    property color accentSurface: appModel.darkMode ? "#263754" : "#dbe7fb"
    property color successColor: appModel.darkMode ? "#75d6a7" : "#237a55"
    property color warningColor: appModel.darkMode ? "#f0bc68" : "#a45b00"
    property color dangerColor: appModel.darkMode ? "#ff9494" : "#b52c3b"

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
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                width: 9
                height: 9
                radius: 5
                color: root.panelColor
                border.color: root.textColor
                border.width: 2
            }
        }
    }

    component AppButton: Button {
        id: control
        implicitHeight: 38
        leftPadding: 15
        rightPadding: 15
        font.family: "Segoe UI Variable"
        font.pixelSize: 13
        font.weight: Font.Medium
        contentItem: Text {
            text: control.text
            font: control.font
            color: control.enabled ? (control.highlighted ? "#ffffff" : root.textColor) : root.mutedColor
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 8
            color: control.enabled
                ? (control.highlighted ? root.accentColor : (control.hovered ? root.accentSurface : root.panelAltColor))
                : (root.darkMode ? "#1a2230" : "#edf0f4")
            border.color: control.highlighted ? "transparent" : root.borderColor
        }
    }

    component NavButton: Button {
        id: nav
        required property int pageIndex
        required property string glyph
        checkable: true
        checked: root.currentPage === pageIndex
        implicitHeight: 42
        leftPadding: 12
        rightPadding: 12
        onClicked: root.currentPage = pageIndex
        background: Rectangle {
            radius: 9
            color: nav.checked ? root.accentSurface : (nav.hovered ? (root.darkMode ? "#1d2736" : "#e1e8f2") : "transparent")
            Rectangle {
                visible: nav.checked
                width: 3
                height: 20
                radius: 2
                anchors.left: parent.left
                anchors.leftMargin: 2
                anchors.verticalCenter: parent.verticalCenter
                color: root.accentColor
            }
        }
        contentItem: RowLayout {
            spacing: 11
            Text {
                text: nav.glyph
                color: nav.checked ? root.accentColor : root.mutedColor
                font.pixelSize: 16
                horizontalAlignment: Text.AlignHCenter
                Layout.preferredWidth: 22
            }
            Text {
                text: nav.text
                color: nav.checked ? root.textColor : root.mutedColor
                font.family: "Segoe UI Variable"
                font.pixelSize: 13
                font.weight: nav.checked ? Font.Medium : Font.Normal
                visible: sidebar.width > 76
                Layout.fillWidth: true
            }
        }
    }

    component Panel: Rectangle {
        color: root.panelColor
        radius: 13
        border.color: root.borderColor
        border.width: 1
    }

    component PageHeading: RowLayout {
        required property string title
        required property string subtitle
        Layout.fillWidth: true
        spacing: 16
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3
            Text {
                text: title
                color: root.textColor
                font.family: "Segoe UI Variable Display"
                font.pixelSize: 24
                font.weight: Font.Medium
            }
            Text {
                text: subtitle
                color: root.mutedColor
                font.family: "Segoe UI Variable"
                font.pixelSize: 12
            }
        }
    }

    component MetricCard: Panel {
        required property string label
        required property string value
        implicitHeight: 88
        Layout.fillWidth: true
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 15
            spacing: 5
            Text { text: label; color: root.mutedColor; font.pixelSize: 11; font.family: "Segoe UI Variable" }
            Text { text: value; color: root.textColor; font.pixelSize: 21; font.weight: Font.Medium; font.family: "Segoe UI Variable Display" }
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
            Behavior on width { NumberAnimation { duration: 420; easing.type: Easing.OutCubic } }
        }
    }

    component ToggleRow: RowLayout {
        id: toggleRow
        required property string label
        property string detail: ""
        property alias checked: toggle.checked
        signal changed(bool value)
        Layout.fillWidth: true
        spacing: 16
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text { text: toggleRow.label; color: root.textColor; font.pixelSize: 13; font.family: "Segoe UI Variable"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { visible: toggleRow.detail.length > 0; text: toggleRow.detail; color: root.mutedColor; font.pixelSize: 11; font.family: "Segoe UI Variable"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
        Switch {
            id: toggle
            onToggled: toggleRow.changed(checked)
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: sidebar
            Layout.preferredWidth: root.width < 900 ? 68 : 190
            Layout.fillHeight: true
            color: root.sidebarColor
            border.color: root.borderColor
            border.width: 0

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 4

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 52
                    Layout.leftMargin: 8
                    spacing: 10
                    PokeBall { }
                    Text {
                        visible: sidebar.width > 76
                        text: "PokeTokenBar"
                        color: root.textColor
                        font.family: "Segoe UI Variable Display"
                        font.pixelSize: 15
                        font.weight: Font.Medium
                    }
                }

                NavButton { pageIndex: 0; glyph: "⌂"; text: "Inicio"; Layout.fillWidth: true }
                NavButton { pageIndex: 1; glyph: "◆"; text: "Colección"; Layout.fillWidth: true }
                NavButton { pageIndex: 2; glyph: "▣"; text: "Bolsa"; Layout.fillWidth: true }
                NavButton { pageIndex: 3; glyph: "◇"; text: "Tienda"; Layout.fillWidth: true }
                NavButton { pageIndex: 4; glyph: "⚙"; text: "Ajustes"; Layout.fillWidth: true }

                Item { Layout.fillHeight: true }

                Rectangle {
                    visible: sidebar.width > 76
                    Layout.fillWidth: true
                    Layout.preferredHeight: 58
                    radius: 9
                    color: root.panelAltColor
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 9
                        Rectangle { width: 8; height: 8; radius: 4; color: appModel.loading ? root.warningColor : root.successColor }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text { text: appModel.loading ? "Cargando" : "Supervisión activa"; color: root.textColor; font.pixelSize: 11; font.weight: Font.Medium }
                            Text { text: appModel.statusText; color: root.mutedColor; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                    }
                }
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.currentPage

            ScrollView {
                id: homePage
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: homePage.availableWidth
                    spacing: 14
                    anchors.margins: 0
                    Item { Layout.preferredHeight: 8 }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        Layout.rightMargin: 24
                        spacing: 16
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3
                            Text { text: "Tu compañero"; color: root.textColor; font.pixelSize: 24; font.weight: Font.Medium; font.family: "Segoe UI Variable Display" }
                            Text { text: "Uso local, límites y progreso en un solo lugar"; color: root.mutedColor; font.pixelSize: 12 }
                        }
                        AppButton {
                            text: appModel.refreshEnabled ? "↻  Actualizar" : "Actualizando…"
                            highlighted: true
                            enabled: appModel.refreshEnabled
                            onClicked: appModel.requestRefresh()
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        Layout.rightMargin: 24
                        columns: width > 760 ? 2 : 1
                        columnSpacing: 14
                        rowSpacing: 14

                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 250
                            Layout.columnSpan: 1
                            gradient: Gradient {
                                GradientStop { position: 0; color: root.panelColor }
                                GradientStop { position: 1; color: root.darkMode ? "#1b2a41" : "#eaf2ff" }
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 22
                                spacing: 20
                                Rectangle {
                                    Layout.preferredWidth: 148
                                    Layout.preferredHeight: 148
                                    radius: 32
                                    color: root.accentSurface
                                    AnimatedImage {
                                        id: companionImage
                                        anchors.fill: parent
                                        anchors.margins: 10
                                        source: appModel.spriteUrl
                                        fillMode: Image.PreserveAspectFit
                                        playing: true
                                        opacity: appModel.loading ? 0.22 : 1
                                        scale: appModel.revealActive ? 1.08 : 1
                                        Behavior on opacity { NumberAnimation { duration: 380 } }
                                        Behavior on scale { NumberAnimation { duration: 360; easing.type: Easing.OutBack } }
                                    }
                                    BusyIndicator { anchors.centerIn: parent; running: appModel.loading; visible: running }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Text { text: "COMPAÑERO ACTUAL"; color: root.mutedColor; font.pixelSize: 10; font.letterSpacing: 1.2 }
                                    Text { text: appModel.companionName; color: root.textColor; font.pixelSize: 23; font.weight: Font.Medium; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: appModel.companionSubtitle; color: root.mutedColor; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    Item { Layout.preferredHeight: 5 }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: appModel.companionProgressText; color: root.mutedColor; font.pixelSize: 11; Layout.fillWidth: true }
                                        Text { text: appModel.companionProgress + "%"; color: root.textColor; font.pixelSize: 11; font.weight: Font.Medium }
                                    }
                                    ModernProgress { value: appModel.companionProgress; Layout.fillWidth: true }
                                }
                            }
                        }

                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 250
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 16
                                spacing: 8
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Límites oficiales"; color: root.textColor; font.pixelSize: 14; font.weight: Font.Medium; Layout.fillWidth: true }
                                    Text { text: appModel.limitDisplayMode === "remaining" ? "RESTANTE" : "USADO"; color: root.mutedColor; font.pixelSize: 9; font.letterSpacing: 1 }
                                }
                                Text { visible: appModel.limits.length === 0; text: appModel.loading ? "Consultando límites…" : "No hay límites oficiales disponibles"; color: root.mutedColor; font.pixelSize: 12 }
                                Repeater {
                                    model: appModel.limits.slice(0, 3)
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 4
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Text { text: modelData.provider + " · " + modelData.label; color: root.textColor; font.pixelSize: 11; font.weight: Font.Medium; Layout.fillWidth: true; elide: Text.ElideRight }
                                            Text { text: modelData.percentText; color: modelData.urgency === "critical" ? root.dangerColor : (modelData.urgency === "warning" ? root.warningColor : root.textColor); font.pixelSize: 11; font.weight: Font.Medium }
                                        }
                                        ModernProgress { value: modelData.percent; barColor: modelData.urgency === "critical" ? root.dangerColor : (modelData.urgency === "warning" ? root.warningColor : root.accentColor); Layout.fillWidth: true }
                                        Text { text: modelData.reset; color: root.mutedColor; font.pixelSize: 9 }
                                    }
                                }
                                Item { Layout.fillHeight: true }
                            }
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        Layout.rightMargin: 24
                        columns: width > 680 ? 4 : 2
                        columnSpacing: 10
                        rowSpacing: 10
                        MetricCard { label: "Tokens hoy"; value: appModel.todayTokens }
                        MetricCard { label: "Coste estimado"; value: appModel.todayCost }
                        MetricCard { label: "Esta semana"; value: appModel.weekTokens }
                        MetricCard { label: "Monedero"; value: appModel.wallet }
                    }

                    Panel {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        Layout.rightMargin: 24
                        Layout.preferredHeight: Math.max(92, 48 + appModel.providers.length * 47)
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 5
                            Text { text: "Proveedores"; color: root.textColor; font.pixelSize: 14; font.weight: Font.Medium }
                            Text { visible: appModel.providers.length === 0; text: appModel.loading ? "Leyendo el uso local…" : "Todavía no se encontraron registros compatibles"; color: root.mutedColor; font.pixelSize: 12 }
                            Repeater {
                                model: appModel.providers
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 42
                                    radius: 8
                                    color: root.panelAltColor
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 11
                                        anchors.rightMargin: 11
                                        Text { text: modelData.name; color: modelData.error ? root.warningColor : root.textColor; font.pixelSize: 12; font.weight: Font.Medium; Layout.fillWidth: true }
                                        Text { text: modelData.today + " hoy"; color: root.textColor; font.pixelSize: 11 }
                                        Text { text: modelData.week + " semana"; color: root.mutedColor; font.pixelSize: 11 }
                                    }
                                }
                            }
                        }
                    }
                    Item { Layout.preferredHeight: 14 }
                }
            }

            ScrollView {
                id: collectionPage
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: collectionPage.availableWidth
                    spacing: 14
                    Item { Layout.preferredHeight: 8 }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        Layout.rightMargin: 24
                        ColumnLayout {
                            Layout.fillWidth: true
                            Text { text: "Colección"; color: root.textColor; font.pixelSize: 24; font.weight: Font.Medium }
                            Text { text: appModel.catches.length + " capturas · elige qué Pokémon te representa"; color: root.mutedColor; font.pixelSize: 12 }
                        }
                        ComboBox {
                            id: representativeCombo
                            Layout.preferredWidth: 230
                            model: appModel.collection
                            textRole: "name"
                            function selectedIndex() {
                                for (var i = 0; i < appModel.collection.length; ++i)
                                    if (appModel.collection[i].selected) return i
                                return 0
                            }
                            Component.onCompleted: currentIndex = selectedIndex()
                            onActivated: appModel.chooseRepresentative(currentIndex)
                            Connections {
                                target: appModel
                                function onDataChanged() { representativeCombo.currentIndex = representativeCombo.selectedIndex() }
                            }
                        }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        Layout.rightMargin: 24
                        columns: width > 760 ? 4 : (width > 480 ? 3 : 2)
                        columnSpacing: 10
                        rowSpacing: 10
                        Repeater {
                            model: appModel.collection.slice(1)
                            Panel {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 158
                                color: modelData.selected ? root.accentSurface : root.panelColor
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 3
                                    AnimatedImage { source: modelData.sprite; playing: true; fillMode: Image.PreserveAspectFit; Layout.fillWidth: true; Layout.preferredHeight: 88 }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: modelData.number; color: root.mutedColor; font.pixelSize: 10; Layout.fillWidth: true }
                                        Text { visible: modelData.shiny; text: "✨"; font.pixelSize: 11 }
                                    }
                                    Text { text: modelData.name; color: root.textColor; font.pixelSize: 12; font.weight: Font.Medium; elide: Text.ElideRight; Layout.fillWidth: true }
                                }
                            }
                        }
                    }
                    Text { visible: appModel.collection.length <= 1; Layout.leftMargin: 24; text: "Eclosiona tu primer huevo para comenzar la colección."; color: root.mutedColor; font.pixelSize: 12 }
                    Text { Layout.leftMargin: 24; text: "Historial de capturas"; color: root.textColor; font.pixelSize: 16; font.weight: Font.Medium }
                    Repeater {
                        model: appModel.catches
                        Panel {
                            Layout.fillWidth: true
                            Layout.leftMargin: 24
                            Layout.rightMargin: 24
                            Layout.preferredHeight: 82
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                AnimatedImage { source: modelData.sprite; playing: true; fillMode: Image.PreserveAspectFit; Layout.preferredWidth: 62; Layout.fillHeight: true }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Text { text: modelData.name + (modelData.shiny ? "  ✨" : ""); color: root.textColor; font.pixelSize: 13; font.weight: Font.Medium }
                                    Text { text: modelData.number + " · " + modelData.meta; color: root.mutedColor; font.pixelSize: 11 }
                                }
                            }
                        }
                    }
                    Item { Layout.preferredHeight: 18 }
                }
            }

            ScrollView {
                id: bagPage
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: bagPage.availableWidth
                    spacing: 14
                    Item { Layout.preferredHeight: 8 }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        Layout.rightMargin: 24
                        ColumnLayout {
                            Layout.fillWidth: true
                            Text { text: "Bolsa"; color: root.textColor; font.pixelSize: 24; font.weight: Font.Medium }
                            Text { text: "Objetos disponibles para tu compañero"; color: root.mutedColor; font.pixelSize: 12 }
                        }
                        Text { text: "Monedero  " + appModel.wallet; color: root.textColor; font.pixelSize: 13; font.weight: Font.Medium }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        Layout.rightMargin: 24
                        columns: width > 560 ? 2 : 1
                        columnSpacing: 12
                        rowSpacing: 12
                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 156
                            RowLayout {
                                anchors.fill: parent; anchors.margins: 18; spacing: 16
                                Text { text: "🍬"; font.pixelSize: 42 }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Rare Candy"; color: root.textColor; font.pixelSize: 16; font.weight: Font.Medium }
                                    Text { text: appModel.rareCandyCount + " disponibles"; color: root.mutedColor; font.pixelSize: 12 }
                                    AppButton { text: "Usar en el compañero"; enabled: appModel.rareCandyCount > 0; onClicked: appModel.useItem("rare_candy") }
                                }
                            }
                        }
                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 156
                            RowLayout {
                                anchors.fill: parent; anchors.margins: 18; spacing: 16
                                Text { text: "🌿"; font.pixelSize: 42 }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Mint"; color: root.textColor; font.pixelSize: 16; font.weight: Font.Medium }
                                    Text { text: appModel.mintCount + " disponibles"; color: root.mutedColor; font.pixelSize: 12 }
                                    AppButton { text: "Cambiar naturaleza"; enabled: appModel.mintCount > 0; onClicked: appModel.useItem("mint") }
                                }
                            }
                        }
                        Panel {
                            Layout.fillWidth: true
                            Layout.columnSpan: width > 560 ? 2 : 1
                            Layout.preferredHeight: 100
                            RowLayout {
                                anchors.fill: parent; anchors.margins: 18; spacing: 16
                                Text { text: "✨"; font.pixelSize: 36 }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Shiny Charm"; color: root.textColor; font.pixelSize: 15; font.weight: Font.Medium }
                                    Text { text: appModel.shinyCharmActive ? "Activo · mejora las probabilidades de futuros shiny" : "No está activo"; color: appModel.shinyCharmActive ? root.successColor : root.mutedColor; font.pixelSize: 12 }
                                }
                            }
                        }
                    }
                }
            }

            ScrollView {
                id: shopPage
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: shopPage.availableWidth
                    spacing: 14
                    Item { Layout.preferredHeight: 8 }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        Layout.rightMargin: 24
                        ColumnLayout {
                            Layout.fillWidth: true
                            Text { text: "Tienda"; color: root.textColor; font.pixelSize: 24; font.weight: Font.Medium }
                            Text { text: "Gasta únicamente los tokens observados desde la instalación"; color: root.mutedColor; font.pixelSize: 12 }
                        }
                        Text { text: "Monedero  " + appModel.wallet; color: root.textColor; font.pixelSize: 13; font.weight: Font.Medium }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        Layout.rightMargin: 24
                        columns: width > 720 ? 3 : (width > 460 ? 2 : 1)
                        columnSpacing: 12
                        rowSpacing: 12
                        Repeater {
                            model: appModel.shopItems
                            Panel {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 190
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 16
                                    spacing: 6
                                    Text { text: modelData.icon; font.pixelSize: 35 }
                                    Text { text: modelData.title; color: root.textColor; font.pixelSize: 15; font.weight: Font.Medium }
                                    Text { text: modelData.subtitle; color: root.mutedColor; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                                    Item { Layout.fillHeight: true }
                                    AppButton {
                                        Layout.fillWidth: true
                                        text: modelData.owned ? "Ya está activo" : modelData.price + " tokens"
                                        highlighted: modelData.enabled
                                        enabled: modelData.enabled
                                        onClicked: appModel.buy(modelData.kind, modelData.key)
                                    }
                                }
                            }
                        }
                    }
                    Item { Layout.preferredHeight: 18 }
                }
            }

            ScrollView {
                id: settingsPage
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: settingsPage.availableWidth
                    spacing: 12
                    Item { Layout.preferredHeight: 8 }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        Layout.rightMargin: 24
                        Text { text: "Ajustes"; color: root.textColor; font.pixelSize: 24; font.weight: Font.Medium }
                        Text { text: "Personaliza la supervisión, la mascota y el aspecto"; color: root.mutedColor; font.pixelSize: 12 }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        Layout.rightMargin: 24
                        columns: width > 700 ? 2 : 1
                        columnSpacing: 12
                        rowSpacing: 12

                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 210
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 16; spacing: 10
                                Text { text: "General"; color: root.textColor; font.pixelSize: 15; font.weight: Font.Medium }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Intervalo de actualización"; color: root.textColor; font.pixelSize: 12; Layout.fillWidth: true }
                                    ComboBox {
                                        model: [1, 2, 5, 10, 15]
                                        currentIndex: Math.max(0, model.indexOf(appModel.refreshMinutes))
                                        delegate: ItemDelegate { required property var modelData; width: parent ? parent.width : 100; text: modelData + " min" }
                                        contentItem: Text { text: parent.currentText + " min"; color: root.textColor; verticalAlignment: Text.AlignVCenter; leftPadding: 8 }
                                        onActivated: appModel.setRefreshMinutes(model[currentIndex])
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Nombres Pokémon"; color: root.textColor; font.pixelSize: 12; Layout.fillWidth: true }
                                    ComboBox {
                                        id: languageCombo
                                        model: [{label: "English", key: "en"}, {label: "Español", key: "es"}, {label: "Français", key: "fr"}, {label: "日本語", key: "ja"}]
                                        textRole: "label"
                                        currentIndex: ["en", "es", "fr", "ja"].indexOf(appModel.language)
                                        onActivated: appModel.setLanguage(model[currentIndex].key)
                                    }
                                }
                                ToggleRow { label: "Iniciar automáticamente con Windows"; checked: appModel.autostart; onChanged: value => appModel.setAutostart(value) }
                            }
                        }

                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 210
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 16; spacing: 8
                                Text { text: "Mascota de escritorio"; color: root.textColor; font.pixelSize: 15; font.weight: Font.Medium }
                                ToggleRow { label: "Mostrar compañero flotante"; checked: appModel.petEnabled; onChanged: value => appModel.setPetEnabled(value) }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Tamaño"; color: root.textColor; font.pixelSize: 12 }
                                    Slider { Layout.fillWidth: true; from: 64; to: 192; stepSize: 8; value: appModel.petSize; enabled: appModel.petEnabled; onMoved: appModel.setPetSize(value) }
                                    Text { text: appModel.petSize + " px"; color: root.mutedColor; font.pixelSize: 11 }
                                }
                                ToggleRow { label: "Burbujas de uso y reinicios"; checked: appModel.petAlerts; onChanged: value => appModel.setPreference("petAlerts", value) }
                            }
                        }

                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 250
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 16; spacing: 8
                                Text { text: "Límites y avisos"; color: root.textColor; font.pixelSize: 15; font.weight: Font.Medium }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Mostrar cuota"; color: root.textColor; font.pixelSize: 12; Layout.fillWidth: true }
                                    ComboBox { model: ["Usada", "Restante"]; currentIndex: appModel.limitDisplayMode === "remaining" ? 1 : 0; onActivated: appModel.setPreference("limitDisplayMode", currentIndex === 1 ? "remaining" : "used") }
                                }
                                ToggleRow { label: "Pronóstico para la ventana de 5 horas"; checked: appModel.forecastEnabled; onChanged: value => appModel.setPreference("forecastEnabled", value) }
                                ToggleRow { label: "Notificaciones de límites"; checked: appModel.limitNotifications; onChanged: value => appModel.setPreference("limitNotifications", value) }
                                ToggleRow { label: "Notificaciones de eventos Pokémon"; checked: appModel.companionNotifications; onChanged: value => appModel.setPreference("companionNotifications", value) }
                            }
                        }

                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 250
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 16; spacing: 9
                                Text { text: "Aspecto y datos"; color: root.textColor; font.pixelSize: 15; font.weight: Font.Medium }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Tema"; color: root.textColor; font.pixelSize: 12; Layout.fillWidth: true }
                                    ComboBox { model: ["Sistema", "Claro", "Oscuro"]; currentIndex: appModel.theme === "light" ? 1 : (appModel.theme === "dark" ? 2 : 0); onActivated: appModel.setPreference("theme", ["system", "light", "dark"][currentIndex]) }
                                }
                                ToggleRow { label: "Tokens de hoy en la bandeja"; checked: appModel.trayShowTokens; onChanged: value => appModel.setPreference("trayShowTokens", value) }
                                ToggleRow { label: "Coste estimado en la bandeja"; checked: appModel.trayShowCost; onChanged: value => appModel.setPreference("trayShowCost", value) }
                                RowLayout {
                                    Layout.fillWidth: true
                                    AppButton { text: "Exportar copia…"; onClicked: appModel.requestExport() }
                                    AppButton { text: "Importar copia…"; onClicked: appModel.requestImport() }
                                }
                            }
                        }
                    }
                    Item { Layout.preferredHeight: 18 }
                }
            }
        }
    }

    Rectangle {
        visible: appModel.feedbackText.length > 0
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 18
        width: Math.min(parent.width - 40, feedbackText.implicitWidth + 34)
        height: 42
        radius: 10
        color: root.darkMode ? "#dce7ff" : "#21365e"
        z: 30
        Text {
            id: feedbackText
            anchors.centerIn: parent
            text: appModel.feedbackText
            color: root.darkMode ? "#17233c" : "#ffffff"
            font.pixelSize: 12
        }
    }

    Rectangle {
        visible: appModel.toastText.length > 0
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.topMargin: 16
        width: Math.min(parent.width - 40, toastText.implicitWidth + 46)
        height: 48
        radius: 12
        color: appModel.toastShiny ? (root.darkMode ? "#4b3e17" : "#fff2bd") : root.panelColor
        border.color: appModel.toastShiny ? root.warningColor : root.borderColor
        z: 40
        Text {
            id: toastText
            anchors.centerIn: parent
            text: (appModel.toastShiny ? "✨  " : "") + appModel.toastText
            color: root.textColor
            font.pixelSize: 13
            font.weight: Font.Medium
        }
    }
}
