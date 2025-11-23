"""Multi-page Workout Tracker with Calendar and Session views."""

import os
from datetime import date, datetime
from calendar import monthrange
from zoneinfo import ZoneInfo
from nicegui import ui, app
from app import workout_data
from app import body_composition_data
import plotly.graph_objects as go
from app.mqtt_service import MQTTService

# Pacific timezone
PACIFIC_TZ = ZoneInfo("America/Los_Angeles")


def create_connection_status():
    """Create a connection status indicator that monitors WebSocket connection."""
    with ui.row().classes(
        "fixed top-2 right-2 z-50 items-center gap-2"
    ) as status_container:
        ui.badge("Connected", color="positive").classes("px-3 py-1")

        # Heartbeat mechanism - ping server every 20 seconds to keep connection alive
        last_ping = {"time": datetime.now(PACIFIC_TZ)}

        def heartbeat_ping():
            """Send a heartbeat ping to keep the connection alive."""
            try:
                last_ping["time"] = datetime.now(PACIFIC_TZ)
                # This simple UI update acts as a keepalive
                pass
            except Exception:
                pass

        # Create a timer that runs every 20 seconds
        ui.timer(20.0, heartbeat_ping)

        # JavaScript to monitor connection state
        ui.add_head_html("""
            <script>
            (function() {
                let isConnected = true;
                let reconnectAttempts = 0;
                const maxReconnectAttempts = 10;
                let lastHeartbeat = Date.now();

                // Find the status badge element
                function updateConnectionStatus(connected, reconnecting = false) {
                    const badge = document.querySelector('.fixed.top-2.right-2 .q-badge');
                    if (!badge) return;

                    if (reconnecting) {
                        badge.textContent = 'Reconnecting...';
                        badge.className = 'q-badge flex inline items-center no-wrap q-badge--single-line bg-warning text-white px-3 py-1';
                    } else if (connected) {
                        badge.textContent = 'Connected';
                        badge.className = 'q-badge flex inline items-center no-wrap q-badge--single-line bg-positive text-white px-3 py-1';
                        reconnectAttempts = 0;
                    } else {
                        badge.textContent = 'Disconnected';
                        badge.className = 'q-badge flex inline items-center no-wrap q-badge--single-line bg-negative text-white px-3 py-1';
                    }
                }

                // Client-side heartbeat - send ping every 15 seconds
                function sendHeartbeat() {
                    if (isConnected && window.socket && window.socket.readyState === WebSocket.OPEN) {
                        try {
                            // Send a ping frame (some WebSocket servers support this)
                            if (window.socket.ping) {
                                window.socket.ping();
                            }
                            lastHeartbeat = Date.now();
                        } catch (e) {
                            console.log('Heartbeat ping failed:', e);
                        }
                    }
                }

                // Monitor WebSocket connection via NiceGUI's internal connection
                function monitorConnection() {
                    // Check if window.socket exists (NiceGUI's WebSocket)
                    if (window.socket) {
                        const originalOnClose = window.socket.onclose;
                        const originalOnOpen = window.socket.onopen || function() {};
                        const originalOnError = window.socket.onerror || function() {};

                        window.socket.onopen = function(event) {
                            isConnected = true;
                            updateConnectionStatus(true);
                            lastHeartbeat = Date.now();
                            originalOnOpen.call(this, event);
                        };

                        window.socket.onclose = function(event) {
                            isConnected = false;
                            updateConnectionStatus(false, reconnectAttempts < maxReconnectAttempts);
                            reconnectAttempts++;
                            if (originalOnClose) originalOnClose.call(this, event);
                        };

                        window.socket.onerror = function(event) {
                            isConnected = false;
                            updateConnectionStatus(false);
                            originalOnError.call(this, event);
                        };
                    }

                    // Also monitor online/offline events
                    window.addEventListener('online', function() {
                        updateConnectionStatus(true, !isConnected);
                    });

                    window.addEventListener('offline', function() {
                        updateConnectionStatus(false);
                    });

                    // Check connection state periodically
                    setInterval(function() {
                        const nowOnline = navigator.onLine;
                        if (!nowOnline && isConnected) {
                            isConnected = false;
                            updateConnectionStatus(false);
                        }

                        // Check if heartbeat is stale (no activity for 45 seconds)
                        const timeSinceHeartbeat = Date.now() - lastHeartbeat;
                        if (isConnected && timeSinceHeartbeat > 45000) {
                            console.log('Connection may be stale, checking...');
                            sendHeartbeat();
                        }
                    }, 5000);

                    // Send heartbeat every 15 seconds
                    setInterval(sendHeartbeat, 15000);
                }

                // Initialize monitoring after page loads
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', monitorConnection);
                } else {
                    setTimeout(monitorConnection, 100);
                }
            })();
            </script>
        """)

    return status_container


def create_nav_bar(current_page: str, page_title: str):
    """Create a consistent navigation bar for all pages.

    Args:
        current_page: One of 'calendar', 'body-comp', 'main-lifts', 'upcoming'
        page_title: Title to display on the left side
    """
    with ui.row().classes("w-full justify-between items-center mb-6"):
        ui.label(page_title).classes("text-3xl font-bold")
        with ui.row().classes("gap-2"):
            if current_page != "calendar":
                ui.button("📅 Calendar", on_click=lambda: ui.navigate.to("/")).props(
                    "flat"
                )
            if current_page != "body-comp":
                ui.button(
                    "⚖️ Body Comp", on_click=lambda: ui.navigate.to("/body-composition")
                ).props("flat")
            if current_page != "main-lifts":
                ui.button(
                    "💪 Main Lifts", on_click=lambda: ui.navigate.to("/progression")
                ).props("flat")
            if current_page != "upcoming":
                ui.button(
                    "📋 Upcoming", on_click=lambda: ui.navigate.to("/upcoming")
                ).props("flat")


@ui.page("/")
def calendar_view():
    """Calendar view - main page showing all workout dates."""
    ui.page_title("Workout Calendar")
    ui.dark_mode().enable()
    create_connection_status()

    with ui.card().classes("w-full max-w-6xl mx-auto mt-8 p-6"):
        create_nav_bar("calendar", "Workout Calendar")

        # Get workout counts for highlighting
        workout_counts = workout_data.get_workout_count_by_date()

        # Current month/year selector (use Pacific time)
        today = datetime.now(PACIFIC_TZ).date()
        current_month = app.storage.user.get("current_month", today.month)
        current_year = app.storage.user.get("current_year", today.year)

        def create_calendar():
            """Create calendar grid for the current month/year."""
            # Month/Year navigation
            with ui.row().classes("w-full justify-between items-center mb-4"):
                ui.button("←", on_click=lambda: change_month(-1)).props("flat dense")
                ui.label(
                    f"{datetime(current_year, current_month, 1).strftime('%B %Y')}"
                ).classes("text-2xl font-semibold")
                ui.button("→", on_click=lambda: change_month(1)).props("flat dense")

            # Weekday headers
            with ui.row().classes("w-full gap-1 sm:gap-2"):
                for day in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
                    ui.label(day).classes(
                        "flex-1 text-center font-bold text-xs sm:text-base"
                    )

            # Calendar grid
            first_day, num_days = monthrange(current_year, current_month)
            day_num = 1

            # Create weeks
            for week in range(6):
                with ui.row().classes("w-full gap-1 sm:gap-2"):
                    for weekday in range(7):
                        # Empty cells before first day
                        if week == 0 and weekday < first_day:
                            ui.label("").classes("flex-1 h-16 sm:h-20 md:h-24")
                        # Empty cells after last day
                        elif day_num > num_days:
                            ui.label("").classes("flex-1 h-16 sm:h-20 md:h-24")
                        # Actual day cells
                        else:
                            day_date = date(current_year, current_month, day_num)
                            day_str = day_date.isoformat()
                            workout_count = workout_counts.get(day_str, 0)

                            # Determine styling based on workout count
                            is_today = day_date == today
                            card_classes = "flex-1 h-16 sm:h-20 md:h-24 cursor-pointer hover:bg-blue-100 p-1 sm:p-2"

                            if is_today:
                                card_classes += " border-2 border-blue-500"

                            if workout_count > 0:
                                card_classes += " bg-green-100"

                            with (
                                ui.card()
                                .classes(card_classes)
                                .on(
                                    "click",
                                    lambda d=day_str: ui.navigate.to(f"/day/{d}"),
                                )
                            ):
                                ui.label(str(day_num)).classes(
                                    "text-sm sm:text-base md:text-lg font-semibold"
                                )
                                if workout_count > 0:
                                    ui.label(f"{workout_count}").classes(
                                        "text-xs text-green-700"
                                    )

                            day_num += 1

                # Stop if we've shown all days
                if day_num > num_days:
                    break

        def change_month(delta):
            """Navigate to previous or next month."""
            nonlocal current_month, current_year
            current_month += delta
            if current_month > 12:
                current_month = 1
                current_year += 1
            elif current_month < 1:
                current_month = 12
                current_year -= 1

            app.storage.user["current_month"] = current_month
            app.storage.user["current_year"] = current_year
            ui.navigate.reload()

        create_calendar()


@ui.page("/day/{selected_date}")
def workout_session_view(selected_date: str):
    """Workout session view for a specific day."""
    ui.page_title(f"Workouts - {selected_date}")
    ui.dark_mode().enable()
    create_connection_status()

    # Initialize offline queue in browser storage
    ui.add_head_html("""
        <script>
        // Offline workout queue management
        (function() {
            const OFFLINE_QUEUE_KEY = 'helf_offline_workout_queue';
            let processingQueue = false;

            window.helfOfflineQueue = {
                add: function(workout) {
                    const queue = this.getQueue();
                    workout._queued_at = new Date().toISOString();
                    queue.push(workout);
                    localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(queue));
                    console.log('Added workout to offline queue:', workout);
                },

                getQueue: function() {
                    const stored = localStorage.getItem(OFFLINE_QUEUE_KEY);
                    return stored ? JSON.parse(stored) : [];
                },

                clear: function() {
                    localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify([]));
                },

                size: function() {
                    return this.getQueue().length;
                },

                processQueue: async function() {
                    if (processingQueue) return;
                    if (!navigator.onLine) return;

                    const queue = this.getQueue();
                    if (queue.length === 0) return;

                    processingQueue = true;
                    console.log('Processing offline queue with', queue.length, 'items');

                    // Clear queue immediately to prevent duplicates
                    this.clear();

                    // Reload page to sync offline data
                    setTimeout(() => {
                        window.location.reload();
                    }, 500);

                    processingQueue = false;
                }
            };

            // Check queue when coming back online
            window.addEventListener('online', function() {
                console.log('Back online, checking offline queue...');
                setTimeout(() => {
                    if (window.helfOfflineQueue.size() > 0) {
                        const msg = `You're back online! Syncing ${window.helfOfflineQueue.size()} workout(s)...`;
                        console.log(msg);
                        window.helfOfflineQueue.processQueue();
                    }
                }, 1000);
            });

            // Show queue size on page load
            window.addEventListener('load', function() {
                const queueSize = window.helfOfflineQueue.size();
                if (queueSize > 0) {
                    console.log('Offline queue has', queueSize, 'pending workouts');
                }
            });
        })();
        </script>
    """)

    with ui.card().classes("w-full max-w-4xl mx-auto mt-8 p-6"):
        # Header with navigation
        with ui.row().classes("w-full justify-between items-center mb-6"):
            ui.button("← Back to Calendar", on_click=lambda: ui.navigate.to("/")).props(
                "flat"
            )
            ui.label(f"Workouts for {selected_date}").classes("text-2xl font-bold")

        # Offline queue indicator (shown when items are queued)
        with ui.row().classes("w-full mb-4 items-center gap-2") as queue_indicator:
            ui.icon("cloud_off", size="sm").classes("text-orange-400")
            ui.label("").classes("text-orange-400 text-sm")
            ui.button(
                "Retry Sync",
                on_click=lambda: ui.run_javascript(
                    "window.helfOfflineQueue.processQueue()"
                ),
            ).props("flat dense color=orange")

        # JavaScript to update queue indicator
        ui.add_head_html("""
            <script>
            (function() {
                function updateQueueIndicator() {
                    const queueSize = window.helfOfflineQueue ? window.helfOfflineQueue.size() : 0;
                    const indicator = document.querySelector('.w-full.mb-4.items-center.gap-2');
                    const label = indicator ? indicator.querySelector('.text-orange-400.text-sm') : null;

                    if (indicator && label) {
                        if (queueSize > 0) {
                            indicator.style.display = 'flex';
                            label.textContent = queueSize + ' workout(s) waiting to sync';
                        } else {
                            indicator.style.display = 'none';
                        }
                    }
                }

                // Update indicator every 2 seconds
                setInterval(updateQueueIndicator, 2000);

                // Initial update
                setTimeout(updateQueueIndicator, 500);

                // Update when coming back online
                window.addEventListener('online', function() {
                    setTimeout(updateQueueIndicator, 500);
                });
            })();
            </script>
        """)

        # Hide queue indicator by default
        queue_indicator.style("display: none")

        # Load existing workouts for this day
        existing_workouts = workout_data.read_workouts_by_date(selected_date)

        # Display existing workouts
        if existing_workouts:
            ui.label("Today's Workouts (click to edit):").classes(
                "text-xl font-semibold mt-4 mb-2"
            )

            # Add indicator column for optional fields
            for workout in existing_workouts:
                has_optional = bool(
                    workout.get("Distance")
                    or workout.get("Time")
                    or workout.get("Comment")
                )
                workout["_indicator"] = "💬" if has_optional else ""

            workout_table = ui.table(
                columns=[
                    {
                        "name": "actions",
                        "label": "",
                        "field": "actions",
                        "align": "center",
                    },
                    {
                        "name": "exercise",
                        "label": "Exercise",
                        "field": "Exercise",
                        "align": "left",
                    },
                    {
                        "name": "category",
                        "label": "Category",
                        "field": "Category",
                        "align": "left",
                    },
                    {
                        "name": "weight",
                        "label": "Weight",
                        "field": "Weight",
                        "align": "left",
                    },
                    {
                        "name": "weight_unit",
                        "label": "Unit",
                        "field": "Weight Unit",
                        "align": "left",
                    },
                    {"name": "reps", "label": "Reps", "field": "Reps", "align": "left"},
                    {
                        "name": "_indicator",
                        "label": "",
                        "field": "_indicator",
                        "align": "center",
                    },
                ],
                rows=existing_workouts,
                row_key="Exercise",
            ).classes("w-full mb-2")

            # Add custom slot for action buttons
            workout_table.add_slot(
                "body-cell-actions",
                """
                <q-td :props="props">
                    <q-btn flat dense round icon="arrow_upward" size="sm" color="primary"
                           @click.stop="$parent.$emit('move_up', props.rowIndex)" />
                    <q-btn flat dense round icon="arrow_downward" size="sm" color="primary"
                           @click.stop="$parent.$emit('move_down', props.rowIndex)" />
                </q-td>
            """,
            )

            # Container for clear button (will be populated after form inputs are created)
            clear_button_container = ui.row().classes("w-full justify-end mb-4")
        else:
            ui.label("No workouts logged for this day yet.").classes(
                "text-gray-500 italic mb-2"
            )

            # Button to add upcoming workout
            def add_upcoming_workout():
                """Add the next upcoming workout session to this day."""
                count = workout_data.pop_upcoming_workout_session(selected_date)
                if count > 0:
                    ui.navigate.reload()
                else:
                    ui.notify("No upcoming workouts available", type="warning")

            ui.button("Add Upcoming Workout", on_click=add_upcoming_workout).props(
                "color=secondary"
            ).classes("mb-4")

            workout_table = None
            clear_button_container = None

        # Divider
        ui.separator().classes("my-6")

        # Form to add new workout
        ui.label("Workout Log").classes("text-xl font-semibold mb-4")

        # Track editing state
        editing_workout = {"original": None, "is_editing": False}

        # Get all exercises grouped by category
        exercises_by_category = workout_data.get_exercises_by_category()
        categories = workout_data.get_categories()

        # Category selection (first field)
        category_options = ["➕ Add new category"] + categories
        category_select = ui.select(
            options=category_options, label="Category", value=None
        ).classes("w-full")

        # Custom category input (hidden by default)
        new_category_input = ui.input(
            label="New Category Name", placeholder="e.g., Chest, Back, Legs"
        ).classes("w-full")
        new_category_input.visible = False

        # Exercise selection (second field)
        exercise_select = ui.select(options=[], label="Exercise", value=None).classes(
            "w-full"
        )

        # Custom exercise input (hidden by default)
        new_exercise_input = ui.input(
            label="New Exercise Name", placeholder="e.g., Flat Barbell Bench Press"
        ).classes("w-full")
        new_exercise_input.visible = False

        def update_exercise_options():
            """Update exercise dropdown based on selected category."""
            if category_select.value == "➕ Add new category":
                # Show new category input, clear exercise options
                new_category_input.visible = True
                exercise_select.options = []
                exercise_select.value = None
                new_exercise_input.visible = False
            elif category_select.value:
                # Hide new category input
                new_category_input.visible = False

                # Get exercises for this category
                category = category_select.value
                exercises = exercises_by_category.get(category, [])

                # Build exercise options
                exercise_opts = ["➕ Add new exercise"] + exercises
                exercise_select.options = exercise_opts
                exercise_select.value = None
                new_exercise_input.visible = False
            else:
                # No category selected
                exercise_select.options = []
                exercise_select.value = None
                new_exercise_input.visible = False

            # Refresh the UI
            exercise_select.update()

        def on_category_change(e):
            """Handle category selection change."""
            update_exercise_options()

        def on_exercise_change(e):
            """Handle exercise selection change."""
            if exercise_select.value == "➕ Add new exercise":
                # Show new exercise input
                new_exercise_input.visible = True
                new_exercise_input.value = ""
            else:
                # Hide new exercise input
                new_exercise_input.visible = False

        # Toggle for showing recent sets
        show_history = ui.checkbox("Show recent sets for reference").classes(
            "mt-4 mb-2"
        )

        # Container for recent sets history
        history_container = (
            ui.column()
            .classes("w-full mb-4")
            .bind_visibility_from(show_history, "value")
        )

        def update_exercise_history():
            """Display recent sets for the selected exercise."""
            history_container.clear()

            # Get exercise name
            exercise_name = None
            if exercise_select.value == "➕ Add new exercise":
                exercise_name = new_exercise_input.value
            elif exercise_select.value:
                exercise_name = exercise_select.value

            if not exercise_name:
                with history_container:
                    ui.label("Select an exercise to see recent sets").classes(
                        "text-sm text-gray-500 italic"
                    )
                return

            # Get recent workouts for this exercise (last 5 workouts)
            all_workouts = workout_data.read_workouts()
            exercise_workouts = [
                w for w in all_workouts if w.get("Exercise") == exercise_name
            ]

            # Sort by date descending and take last 5
            exercise_workouts.sort(key=lambda x: x.get("Date", ""), reverse=True)
            recent_workouts = exercise_workouts[:5]

            if not recent_workouts:
                with history_container:
                    ui.label(f"No previous sets found for {exercise_name}").classes(
                        "text-sm text-gray-500 italic"
                    )
                return

            # Display recent sets
            with history_container:
                ui.label(f"Recent sets for {exercise_name}:").classes(
                    "text-sm font-semibold text-blue-400 mb-2"
                )

                for workout in recent_workouts:
                    weight = workout.get("Weight", "")
                    unit = workout.get("Weight Unit", "lbs")
                    reps = workout.get("Reps", "")
                    date = workout.get("Date", "")
                    comment = workout.get("Comment", "")

                    # Build display string
                    set_info = f"{date}: "
                    if weight:
                        set_info += f"{weight} {unit}"
                    if reps:
                        set_info += f" × {reps} reps"
                    if comment:
                        set_info += f" ({comment})"

                    ui.label(set_info).classes("text-sm text-gray-300")

        # Update history when exercise changes or history checkbox is toggled
        def on_exercise_change_with_history(e):
            """Handle exercise selection change and update history."""
            on_exercise_change(e)
            if show_history.value:
                update_exercise_history()

        # Set up event handlers
        category_select.on("update:model-value", on_category_change)
        exercise_select.on("update:model-value", on_exercise_change_with_history)
        new_exercise_input.on(
            "blur", lambda: update_exercise_history() if show_history.value else None
        )
        show_history.on("update:model-value", lambda: update_exercise_history())

        with ui.row().classes("w-full gap-2"):
            weight_input = ui.number(
                label="Weight", placeholder="0.0", format="%.1f"
            ).classes("flex-1")
            weight_unit_input = ui.select(
                options=["lbs", "kg"], label="Weight Unit", value="lbs"
            ).classes("flex-1")

        reps_input = ui.number(label="Reps", placeholder="0", format="%d").classes(
            "w-full"
        )

        # Toggle for optional fields
        show_optional = ui.checkbox(
            "Show optional fields (Distance, Time, Comment)"
        ).classes("mt-4 mb-2")

        # Optional fields container (hidden by default)
        with (
            ui.column()
            .classes("w-full gap-4")
            .bind_visibility_from(show_optional, "value")
        ):
            with ui.row().classes("w-full gap-2"):
                distance_input = ui.number(
                    label="Distance (optional)", placeholder="0.0", format="%.2f"
                ).classes("flex-1")
                distance_unit_input = ui.select(
                    options=["miles", "km", "meters", "yards"],
                    label="Distance Unit",
                    value="miles",
                ).classes("flex-1")

            time_input = ui.input(
                label="Time (optional)", placeholder="e.g., 00:30:00"
            ).classes("w-full")
            comment_input = ui.textarea(
                label="Comment (optional)", placeholder="Notes about this set"
            ).classes("w-full")

        # Status message
        status_label = ui.label("").classes("text-green-600")

        def populate_form(workout_row):
            """Populate form with workout data from a table row."""
            # Store original workout for editing (remove UI-only fields)
            original = workout_row.copy()
            original.pop("_indicator", None)  # Remove indicator field added for UI
            editing_workout["original"] = original
            editing_workout["is_editing"] = True

            category = workout_row["Category"]
            exercise = workout_row["Exercise"]

            # Set category
            if category in categories:
                category_select.value = category
                new_category_input.visible = False
            else:
                category_select.value = "➕ Add new category"
                new_category_input.visible = True
                new_category_input.value = category

            # Update exercise options based on category
            update_exercise_options()

            # Set exercise
            if (
                category in exercises_by_category
                and exercise in exercises_by_category[category]
            ):
                exercise_select.value = exercise
                new_exercise_input.visible = False
            else:
                exercise_select.value = "➕ Add new exercise"
                new_exercise_input.visible = True
                new_exercise_input.value = exercise

            weight_input.value = (
                float(workout_row["Weight"]) if workout_row["Weight"] else None
            )
            weight_unit_input.value = (
                workout_row["Weight Unit"] if workout_row["Weight Unit"] else "lbs"
            )
            reps_input.value = int(workout_row["Reps"]) if workout_row["Reps"] else None
            distance_input.value = (
                float(workout_row["Distance"]) if workout_row["Distance"] else None
            )
            distance_unit_input.value = (
                workout_row["Distance Unit"]
                if workout_row["Distance Unit"]
                else "miles"
            )
            time_input.value = workout_row["Time"] if workout_row["Time"] else ""
            comment_input.value = (
                workout_row["Comment"] if workout_row["Comment"] else ""
            )

            # Show optional fields if any of them have data
            if workout_row["Distance"] or workout_row["Time"] or workout_row["Comment"]:
                show_optional.value = True

            # Switch to edit mode buttons
            create_button.visible = False
            edit_buttons_row.visible = True
            status_label.text = "Editing workout - choose New Entry, Update, or Delete"
            status_label.classes("text-blue-600")

        def clear_form():
            """Clear all form fields and reset to blank state."""
            # Reset editing state
            editing_workout["original"] = None
            editing_workout["is_editing"] = False

            category_select.value = None
            new_category_input.value = ""
            new_category_input.visible = False
            exercise_select.value = None
            exercise_select.options = []
            new_exercise_input.value = ""
            new_exercise_input.visible = False
            weight_input.value = None
            weight_unit_input.value = "lbs"
            reps_input.value = None
            distance_input.value = None
            distance_unit_input.value = "miles"
            time_input.value = ""
            comment_input.value = ""
            show_optional.value = False

            # Switch to create mode buttons
            create_button.visible = True
            edit_buttons_row.visible = False
            status_label.text = ""

        # Make table rows clickable and add clear button if there are existing workouts
        if existing_workouts:
            workout_table.on("rowClick", lambda e: populate_form(e.args[1]))

            # Add reorder handlers
            def move_workout_up(e):
                """Move workout up in the order."""
                index = e.args
                if workout_data.reorder_workout(selected_date, index, "up"):
                    update_table()
                    ui.notify("Exercise moved up", type="positive")

            def move_workout_down(e):
                """Move workout down in the order."""
                index = e.args
                if workout_data.reorder_workout(selected_date, index, "down"):
                    update_table()
                    ui.notify("Exercise moved down", type="positive")

            workout_table.on("move_up", move_workout_up)
            workout_table.on("move_down", move_workout_down)

            # Add clear button to the container created earlier
            with clear_button_container:
                ui.button("Add New Entry", on_click=clear_form).props(
                    "flat color=primary"
                )

        def get_current_workout_data():
            """Get workout data from current form values."""
            # Determine category name
            if category_select.value == "➕ Add new category":
                category_name = new_category_input.value
            else:
                category_name = category_select.value

            # Determine exercise name
            if exercise_select.value == "➕ Add new exercise":
                exercise_name = new_exercise_input.value
            else:
                exercise_name = exercise_select.value

            return {
                "Date": selected_date,
                "Exercise": exercise_name,
                "Category": category_name,
                "Weight": weight_input.value if weight_input.value else "",
                "Weight Unit": weight_unit_input.value,
                "Reps": int(reps_input.value) if reps_input.value else "",
                "Distance": distance_input.value if distance_input.value else "",
                "Distance Unit": distance_unit_input.value
                if distance_input.value
                else "",
                "Time": time_input.value if time_input.value else "",
                "Comment": comment_input.value.replace('"', '""')
                if comment_input.value
                else "",
            }

        def update_table():
            """Refresh the workout table."""
            if existing_workouts is not None and workout_table is not None:
                updated_workouts = workout_data.read_workouts_by_date(selected_date)
                # Add indicator column for optional fields
                for workout_row in updated_workouts:
                    has_optional = bool(
                        workout_row.get("Distance")
                        or workout_row.get("Time")
                        or workout_row.get("Comment")
                    )
                    workout_row["_indicator"] = "💬" if has_optional else ""
                workout_table.rows = updated_workouts
                workout_table.update()

        def save_workout():
            """Create a new workout entry."""
            workout = get_current_workout_data()

            if not workout["Exercise"] or not workout["Category"]:
                status_label.text = "Error: Exercise and Category are required!"
                status_label.classes("text-red-600")
                return

            try:
                workout_data.write_workout(workout)

                # Only clear optional fields (keep category, exercise, weight, reps for next set)
                distance_input.value = None
                time_input.value = ""
                comment_input.value = ""

                update_table()

                status_label.text = "Set logged! Add another set or change exercise."
                status_label.classes("text-green-600")
            except Exception:
                # If save fails (possibly due to connection issue), show error
                status_label.text = (
                    "Error saving workout. Check connection and try again."
                )
                status_label.classes("text-red-600")
                ui.notify(
                    "Could not save workout. Please check your connection.",
                    type="negative",
                )

        def update_workout_handler():
            """Update the existing workout being edited."""
            if not editing_workout["is_editing"] or not editing_workout["original"]:
                return

            workout = get_current_workout_data()

            if not workout["Exercise"] or not workout["Category"]:
                status_label.text = "Error: Exercise and Category are required!"
                status_label.classes("text-red-600")
                return

            workout_data.update_workout(editing_workout["original"], workout)

            # Reset to create mode
            editing_workout["original"] = None
            editing_workout["is_editing"] = False
            create_button.visible = True
            edit_buttons_row.visible = False

            # Clear optional fields
            distance_input.value = None
            time_input.value = ""
            comment_input.value = ""

            update_table()

            status_label.text = "Workout updated successfully!"
            status_label.classes("text-green-600")

        def delete_workout_handler():
            """Delete the current workout being edited."""
            if not editing_workout["is_editing"] or not editing_workout["original"]:
                return

            workout_data.delete_workout(editing_workout["original"])

            # Clear form and reset state
            clear_form()

            update_table()

            status_label.text = "Workout deleted successfully!"
            status_label.classes("text-green-600")

        # Buttons - different sets for create vs edit mode
        with ui.column().classes("mt-4 gap-2"):
            # Main action buttons row
            with ui.row().classes("gap-2"):
                # Create mode button (default)
                create_button = ui.button("Log Workout", on_click=save_workout).props(
                    "color=primary"
                )

                # Edit mode buttons (hidden by default)
                with ui.row().classes("gap-2") as edit_buttons_row:
                    ui.button(
                        "New Entry", on_click=save_workout
                    ).props("color=primary")
                    ui.button(
                        "Update", on_click=lambda: update_workout_handler()
                    ).props("color=positive")
                    ui.button(
                        "Delete", on_click=delete_workout_handler
                    ).props("color=negative")

                edit_buttons_row.visible = False

            # View progression button (always visible)
            def view_progression():
                """Navigate to progression view for the selected exercise."""
                # Get current exercise
                if exercise_select.value == "➕ Add new exercise":
                    exercise_name = new_exercise_input.value
                elif exercise_select.value:
                    exercise_name = exercise_select.value
                else:
                    ui.notify("Please select an exercise first", type="warning")
                    return

                if exercise_name:
                    # Navigate to progression page with exercise parameter
                    import urllib.parse

                    encoded_exercise = urllib.parse.quote(exercise_name)
                    ui.navigate.to(f"/progression/{encoded_exercise}")
                else:
                    ui.notify("Please select an exercise first", type="warning")

            ui.button("📊 View Progression", on_click=view_progression).props(
                "flat color=secondary"
            ).classes("text-sm")


@ui.page("/progression")
@ui.page("/progression/{exercise_name}")
def progression_view(exercise_name: str = None):
    """Progression tracking view showing main lifts."""
    ui.page_title("Main Lifts")
    ui.dark_mode().enable()
    create_connection_status()

    with ui.card().classes("w-full max-w-7xl mx-auto mt-8 p-6"):
        create_nav_bar("main-lifts", "Main Lifts")

        # Moving average period input
        with ui.row().classes("w-full items-center gap-4 mb-6"):
            ui.label("Moving Average Period:").classes("text-lg font-semibold")
            ma_input = ui.number(
                label="Days", value=30, min=1, max=365, format="%d"
            ).classes("w-32")
            ui.label("(Press Enter to update)").classes("text-sm text-gray-400")

        def create_exercise_chart(exercise_name, title=None, ma_window=30):
            """Create a chart for a specific exercise with 30-day moving average."""
            import numpy as np

            if title is None:
                title = exercise_name

            # Get progression data
            data = workout_data.get_progression_data(exercise_name)
            historical = data["historical"]
            upcoming = data["upcoming"]

            if not historical and not upcoming:
                ui.label(f"No data available for {title}").classes(
                    "text-gray-500 italic text-center my-8"
                )
                return

            # Prepare historical data
            hist_dates = []
            hist_estimated_1rm = []
            hist_labels = []

            for workout in enumerate(historical):
                hist_dates.append(workout[1].get("Date", ""))
                estimated_1rm = workout[1].get("estimated_1rm", 0)
                hist_estimated_1rm.append(estimated_1rm)
                weight = workout[1].get("Weight", "")
                reps = workout[1].get("Reps", "")
                hist_labels.append(
                    f"{weight} lbs x {reps}<br>Est 1RM: {estimated_1rm:.1f} lbs"
                )

            # Prepare upcoming data
            future_dates = []
            future_estimated_1rm = []
            future_labels = []

            for workout in upcoming:
                projected_date = workout.get("projected_date", "")
                future_dates.append(projected_date)
                estimated_1rm = workout.get("estimated_1rm", 0)
                future_estimated_1rm.append(estimated_1rm)
                weight = workout.get("Weight", "")
                reps = workout.get("Reps", "")
                future_labels.append(
                    f"{weight} lbs x {reps}<br>Est 1RM: {estimated_1rm:.1f} lbs"
                )

            # Create plotly figure
            fig = go.Figure()

            # Add historical data (markers only, no lines)
            if hist_estimated_1rm:
                fig.add_trace(
                    go.Scatter(
                        x=hist_dates,
                        y=hist_estimated_1rm,
                        mode="markers",
                        name="Past Workouts",
                        marker=dict(size=8, color="#4CAF50", symbol="circle"),
                        text=hist_labels,
                        hovertemplate="<b>%{x}</b><br>%{text}<extra></extra>",
                    )
                )

            # Add upcoming data (markers only, no lines)
            if future_estimated_1rm:
                fig.add_trace(
                    go.Scatter(
                        x=future_dates,
                        y=future_estimated_1rm,
                        mode="markers",
                        name="Future Workouts (Projected)",
                        marker=dict(size=8, color="#2196F3", symbol="circle"),
                        text=future_labels,
                        hovertemplate="<b>%{x}</b><br>%{text}<extra></extra>",
                    )
                )

            # Calculate moving average for historical data only
            if len(hist_estimated_1rm) >= 2:
                try:
                    # Calculate moving average with dynamic window
                    window_size = min(ma_window, len(hist_estimated_1rm))
                    moving_avg = []

                    for i in range(len(hist_estimated_1rm)):
                        start_idx = max(0, i - window_size + 1)
                        window = hist_estimated_1rm[start_idx : i + 1]
                        moving_avg.append(np.mean(window))

                    fig.add_trace(
                        go.Scatter(
                            x=hist_dates,
                            y=moving_avg,
                            mode="lines",
                            name=f"{ma_window}-Day Average",
                            line=dict(
                                color="#FFD700", width=3, shape="spline", smoothing=1.3
                            ),
                            hovertemplate=f"<b>{ma_window}-Day MA:</b> %{{y:.1f}} lbs<extra></extra>",
                            connectgaps=False,
                        )
                    )
                except (ImportError, ValueError, TypeError):
                    pass

            # Add vertical line to mark today
            if hist_dates and future_dates:
                from datetime import datetime as dt

                last_hist_date = hist_dates[-1]
                first_future_date = future_dates[0]

                try:
                    last_dt = dt.fromisoformat(last_hist_date)
                    first_ft = dt.fromisoformat(first_future_date)
                    midpoint = last_dt + (first_ft - last_dt) / 2

                    fig.add_vline(
                        x=midpoint.isoformat()[:10],
                        line_width=2,
                        line_dash="dash",
                        line_color="gray",
                        annotation_text="Today",
                        annotation_position="top",
                    )
                except (ValueError, TypeError):
                    pass

            fig.update_layout(
                title=title,
                xaxis_title="Date",
                yaxis_title="Estimated 1RM (lbs)",
                hovermode="closest",
                showlegend=True,
                height=400,
                template="plotly_dark",
                xaxis=dict(type="date"),
                margin=dict(l=50, r=50, t=50, b=50),
            )

            ui.plotly(fig).classes("w-full")

        # Container for main charts
        main_charts_container = ui.column().classes("w-full")

        # 4th chart with dropdown for any exercise
        ui.label("Custom Exercise").classes("text-2xl font-bold mt-4 mb-2")

        main_lifts = workout_data.get_main_lifts()
        selected_exercise = {"value": main_lifts[0] if main_lifts else None}

        def on_exercise_change(e):
            """Handle exercise selection change."""
            selected_exercise["value"] = e.value
            update_all_charts()

        with ui.row().classes("w-full mb-4"):
            ui.select(
                options=main_lifts,
                label="Select Exercise",
                value=selected_exercise["value"],
                on_change=on_exercise_change,
            ).classes("w-64")

        custom_chart_container = ui.column().classes("w-full")

        def update_all_charts():
            """Update all charts with current moving average setting."""
            ma_window = (
                int(ma_input.value) if ma_input.value and ma_input.value >= 1 else 30
            )

            # Update main 3 charts
            main_charts_container.clear()
            with main_charts_container:
                main_exercises = [
                    "Flat Barbell Bench Press",
                    "Barbell Squat",
                    "Deadlift",
                ]
                for exercise in main_exercises:
                    create_exercise_chart(exercise, ma_window=ma_window)
                    ui.separator().classes("my-6")

            # Update custom chart
            custom_chart_container.clear()
            if not selected_exercise["value"]:
                with custom_chart_container:
                    ui.label("Please select an exercise").classes(
                        "text-gray-500 italic"
                    )
            else:
                with custom_chart_container:
                    create_exercise_chart(
                        selected_exercise["value"], ma_window=ma_window
                    )

        # Update charts when user presses Enter or leaves the input field
        ma_input.on("keydown.enter", lambda: update_all_charts())
        ma_input.on("blur", lambda: update_all_charts())

        # Initial load with slight delay to ensure UI is ready
        ui.timer(0.1, update_all_charts, once=True)


@ui.page("/upcoming")
def upcoming_workouts_view():
    """View all upcoming workouts grouped by session."""
    ui.page_title("Upcoming Workouts")
    ui.dark_mode().enable()
    create_connection_status()

    with ui.card().classes("w-full max-w-6xl mx-auto mt-8 p-6"):
        create_nav_bar("upcoming", "Upcoming Workouts")

        # Load upcoming workouts
        upcoming_workouts = workout_data.read_upcoming_workouts()

        if not upcoming_workouts:
            ui.label("No upcoming workouts planned.").classes(
                "text-gray-500 italic mb-4"
            )
            ui.label("Add workouts to upcoming_workouts.csv to see them here.").classes(
                "text-sm text-gray-400"
            )
        else:
            # Group workouts by session
            sessions = {}
            for workout in upcoming_workouts:
                session = workout.get("Session", "0")
                if session not in sessions:
                    sessions[session] = []
                sessions[session].append(workout)

            # Display each session
            for session_num in sorted(
                sessions.keys(), key=lambda x: int(x) if x.isdigit() else 0
            ):
                with ui.expansion(
                    f"Session {session_num}", icon="fitness_center"
                ).classes("w-full mb-4"):
                    session_workouts = sessions[session_num]

                    # Add indicator for optional fields
                    for workout in session_workouts:
                        has_optional = bool(
                            workout.get("Distance")
                            or workout.get("Time")
                            or workout.get("Comment")
                        )
                        workout["_indicator"] = "💬" if has_optional else ""

                    # Create table for this session
                    ui.table(
                        columns=[
                            {
                                "name": "exercise",
                                "label": "Exercise",
                                "field": "Exercise",
                                "align": "left",
                            },
                            {
                                "name": "category",
                                "label": "Category",
                                "field": "Category",
                                "align": "left",
                            },
                            {
                                "name": "weight",
                                "label": "Weight",
                                "field": "Weight",
                                "align": "left",
                            },
                            {
                                "name": "weight_unit",
                                "label": "Unit",
                                "field": "Weight Unit",
                                "align": "left",
                            },
                            {
                                "name": "reps",
                                "label": "Reps",
                                "field": "Reps",
                                "align": "left",
                            },
                            {
                                "name": "_indicator",
                                "label": "",
                                "field": "_indicator",
                                "align": "center",
                            },
                        ],
                        rows=session_workouts,
                        row_key="Exercise",
                    ).classes("w-full")

            # Summary stats
            ui.separator().classes("my-6")
            total_sessions = len(sessions)
            total_exercises = len(upcoming_workouts)

            with ui.row().classes("w-full gap-8 justify-center"):
                with ui.card().classes("p-4"):
                    ui.label("Total Sessions").classes("text-sm text-gray-400")
                    ui.label(str(total_sessions)).classes(
                        "text-3xl font-bold text-blue-400"
                    )

                with ui.card().classes("p-4"):
                    ui.label("Total Exercises").classes("text-sm text-gray-400")
                    ui.label(str(total_exercises)).classes(
                        "text-3xl font-bold text-green-400"
                    )


@ui.page("/body-composition")
def body_composition_view():
    """Body composition tracking view with graphs."""
    ui.page_title("Body Composition")
    ui.dark_mode().enable()
    create_connection_status()

    with ui.card().classes("w-full max-w-6xl mx-auto mt-8 p-6"):
        create_nav_bar("body-comp", "Body Composition")

        # Moving average period input
        with ui.row().classes("w-full items-center gap-4 mb-6"):
            ui.label("Moving Average Period:").classes("text-lg font-semibold")
            ma_input = ui.number(
                label="Days", value=7, min=1, max=365, format="%d"
            ).classes("w-32")
            ui.label("(Press Enter to update)").classes("text-sm text-gray-400")

        # Get stats
        stats = body_composition_data.get_stats_summary()
        measurements = body_composition_data.read_measurements()

        # Summary cards
        if stats:
            with ui.row().classes("w-full gap-4 mb-6"):
                # Latest weight
                with ui.card().classes("flex-1 p-4"):
                    ui.label("Current Weight").classes("text-sm text-gray-400")
                    weight_val = stats.get("latest_weight")
                    if weight_val:
                        weight_lbs = weight_val * 2.20462  # Convert kg to lbs in memory
                        ui.label(f"{weight_lbs:.1f} lbs").classes(
                            "text-3xl font-bold text-blue-400"
                        )
                    else:
                        ui.label("—").classes("text-3xl font-bold text-gray-600")

                # Weight change
                with ui.card().classes("flex-1 p-4"):
                    ui.label("Weight Change").classes("text-sm text-gray-400")
                    change = stats.get("weight_change")
                    if change is not None:
                        change_lbs = change * 2.20462  # Convert kg to lbs in memory
                        color = "text-green-400" if change_lbs < 0 else "text-red-400"
                        ui.label(f"{change_lbs:+.1f} lbs").classes(
                            f"text-3xl font-bold {color}"
                        )
                    else:
                        ui.label("—").classes("text-3xl font-bold text-gray-600")

                # Body fat
                with ui.card().classes("flex-1 p-4"):
                    ui.label("Body Fat %").classes("text-sm text-gray-400")
                    bf = stats.get("latest_body_fat")
                    if bf:
                        ui.label(f"{bf:.1f}%").classes(
                            "text-3xl font-bold text-purple-400"
                        )
                    else:
                        ui.label("—").classes("text-3xl font-bold text-gray-600")

                # Total measurements
                with ui.card().classes("flex-1 p-4"):
                    ui.label("Measurements").classes("text-sm text-gray-400")
                    ui.label(str(stats.get("total_measurements", 0))).classes(
                        "text-3xl font-bold text-cyan-400"
                    )

        # Container for graphs
        graphs_container = ui.column().classes("w-full")

        # Helper function to calculate moving average
        def calculate_moving_average(values, window=7):
            """Calculate moving average with given window size."""
            ma = []
            for i in range(len(values)):
                if values[i] is None:
                    ma.append(None)
                else:
                    # Get window of valid values
                    window_values = [
                        v
                        for v in values[max(0, i - window + 1) : i + 1]
                        if v is not None
                    ]
                    if window_values:
                        ma.append(sum(window_values) / len(window_values))
                    else:
                        ma.append(None)
            return ma

        # Helper function to convert kg to lbs in memory
        def kg_to_lbs(kg_value):
            """Convert kg to lbs."""
            if kg_value is None:
                return None
            return kg_value * 2.20462

        def create_graphs():
            """Create all body composition graphs with current moving average setting."""
            ma_window = (
                int(ma_input.value) if ma_input.value and ma_input.value >= 1 else 7
            )

            graphs_container.clear()

            if not measurements:
                with graphs_container:
                    ui.label(
                        "No measurements yet. Step on your scale to start tracking!"
                    ).classes("text-center text-gray-400 mt-8")
                return

            with graphs_container:
                ui.separator().classes("my-6")

                dates = [m["Date"] for m in measurements]
                # Convert weights from kg to lbs in memory for display
                weights_kg = [
                    float(m["Weight"]) if m["Weight"] else None for m in measurements
                ]
                weights = [kg_to_lbs(w) for w in weights_kg]
                body_fats = [
                    float(m["Body Fat %"]) if m.get("Body Fat %") else None
                    for m in measurements
                ]
                muscle_masses = [
                    float(m["Muscle Mass"]) if m.get("Muscle Mass") else None
                    for m in measurements
                ]

                # Calculate moving averages with dynamic window
                weight_ma = calculate_moving_average(weights, window=ma_window)
                body_fat_ma = calculate_moving_average(body_fats, window=ma_window)
                muscle_ma = calculate_moving_average(muscle_masses, window=ma_window)

                # Weight trend graph
                fig_weight = go.Figure()
                fig_weight.add_trace(
                    go.Scatter(
                        x=dates,
                        y=weights,
                        mode="markers",
                        name="Daily Weight",
                        marker=dict(size=6, color="#60A5FA", opacity=0.4),
                        showlegend=True,
                    )
                )
                fig_weight.add_trace(
                    go.Scatter(
                        x=dates,
                        y=weight_ma,
                        mode="lines",
                        name=f"{ma_window}-Day Average",
                        line=dict(
                            color="#60A5FA", width=3, shape="spline", smoothing=1.3
                        ),
                        connectgaps=False,
                        showlegend=True,
                    )
                )
                fig_weight.update_layout(
                    title="Weight Trend",
                    xaxis_title="Date",
                    yaxis_title="Weight (lbs)",
                    template="plotly_dark",
                    height=400,
                    hovermode="x unified",
                )
                ui.plotly(fig_weight).classes("w-full")

                # Body Fat % graph
                if any(body_fats):
                    ui.separator().classes("my-6")

                    fig_fat = go.Figure()
                    fig_fat.add_trace(
                        go.Scatter(
                            x=dates,
                            y=body_fats,
                            mode="markers",
                            name="Daily Body Fat %",
                            marker=dict(size=6, color="#F472B6", opacity=0.4),
                            showlegend=True,
                        )
                    )
                    fig_fat.add_trace(
                        go.Scatter(
                            x=dates,
                            y=body_fat_ma,
                            mode="lines",
                            name=f"{ma_window}-Day Average",
                            line=dict(
                                color="#F472B6", width=3, shape="spline", smoothing=1.3
                            ),
                            connectgaps=False,
                            showlegend=True,
                        )
                    )
                    fig_fat.update_layout(
                        title="Body Fat %",
                        xaxis_title="Date",
                        yaxis_title="Body Fat %",
                        template="plotly_dark",
                        height=400,
                        hovermode="x unified",
                    )
                    ui.plotly(fig_fat).classes("w-full")

                # Muscle Mass graph
                if any(muscle_masses):
                    ui.separator().classes("my-6")

                    fig_muscle = go.Figure()
                    fig_muscle.add_trace(
                        go.Scatter(
                            x=dates,
                            y=muscle_masses,
                            mode="markers",
                            name="Daily Muscle Mass",
                            marker=dict(size=6, color="#34D399", opacity=0.4),
                            showlegend=True,
                        )
                    )
                    fig_muscle.add_trace(
                        go.Scatter(
                            x=dates,
                            y=muscle_ma,
                            mode="lines",
                            name=f"{ma_window}-Day Average",
                            line=dict(
                                color="#34D399", width=3, shape="spline", smoothing=1.3
                            ),
                            connectgaps=False,
                            showlegend=True,
                        )
                    )
                    fig_muscle.update_layout(
                        title="Muscle Mass",
                        xaxis_title="Date",
                        yaxis_title="Muscle Mass (%)",
                        template="plotly_dark",
                        height=400,
                        hovermode="x unified",
                    )
                    ui.plotly(fig_muscle).classes("w-full")

        # Update graphs when user presses Enter or leaves the input field
        ma_input.on("keydown.enter", lambda: create_graphs())
        ma_input.on("blur", lambda: create_graphs())

        # Initial load with slight delay to ensure UI is ready
        ui.timer(0.1, create_graphs, once=True)

        # Recent measurements table
        if measurements:
            ui.separator().classes("my-6")
            ui.label("Recent Measurements").classes("text-2xl font-bold mb-4")

            # Show last 10 measurements
            recent = sorted(measurements, key=lambda x: x["Timestamp"], reverse=True)[
                :10
            ]

            table_data = []
            for m in recent:
                # Convert weight from kg to lbs in memory for display
                weight_kg = float(m["Weight"]) if m["Weight"] else None
                weight_lbs = weight_kg * 2.20462 if weight_kg else None

                row = {
                    "Date": m["Date"],
                    "Weight": f"{weight_lbs:.1f} lbs" if weight_lbs else "—",
                    "Body Fat %": f"{m['Body Fat %']}%" if m.get("Body Fat %") else "—",
                    "Muscle Mass": m.get("Muscle Mass", "—"),
                    "BMI": m.get("BMI", "—"),
                }
                table_data.append(row)

            ui.table(
                columns=[
                    {"name": "Date", "label": "Date", "field": "Date", "align": "left"},
                    {
                        "name": "Weight",
                        "label": "Weight",
                        "field": "Weight",
                        "align": "left",
                    },
                    {
                        "name": "Body Fat %",
                        "label": "Body Fat %",
                        "field": "Body Fat %",
                        "align": "left",
                    },
                    {
                        "name": "Muscle Mass",
                        "label": "Muscle Mass",
                        "field": "Muscle Mass",
                        "align": "left",
                    },
                    {"name": "BMI", "label": "BMI", "field": "BMI", "align": "left"},
                ],
                rows=table_data,
                row_key="Date",
            ).classes("w-full")


# Initialize and start MQTT service
mqtt_broker_host = os.getenv("MQTT_BROKER_HOST", "localhost")
mqtt_broker_port = int(os.getenv("MQTT_BROKER_PORT", "1883"))
mqtt_service = MQTTService(broker_host=mqtt_broker_host, broker_port=mqtt_broker_port)
app.on_startup(lambda: mqtt_service.start())
app.on_shutdown(lambda: mqtt_service.stop())

# Run with NiceGUI's built-in server (which uses Uvicorn)
# Production settings optimized for single user with long idle periods at the gym
ui.run(
    favicon="💪",
    title="Helf - Health & Fitness Tracker",
    port=8080,
    host="0.0.0.0",
    reload=False,
    show=False,
    storage_secret="helf-secret-key-2024",
    reconnect_timeout=3600.0,  # Allow 1 hour to reconnect (basically never timeout at the gym)
    uvicorn_logging_level="info",
    uvicorn_reload_dirs=None,  # Disable file watching
)
