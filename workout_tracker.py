"""Multi-page Workout Tracker with Calendar and Session views."""
from datetime import date, datetime, timedelta
from calendar import monthrange
from nicegui import ui, app
import workout_data
import plotly.graph_objects as go


@ui.page('/')
def calendar_view():
    """Calendar view - main page showing all workout dates."""
    ui.page_title('Workout Calendar')
    ui.dark_mode().enable()

    with ui.card().classes('w-full max-w-6xl mx-auto mt-8 p-6'):
        ui.label('Workout Calendar').classes('text-3xl font-bold mb-6')

        # Get workout counts for highlighting
        workout_counts = workout_data.get_workout_count_by_date()

        # Current month/year selector
        today = date.today()
        current_month = app.storage.user.get('current_month', today.month)
        current_year = app.storage.user.get('current_year', today.year)

        def create_calendar():
            """Create calendar grid for the current month/year."""
            # Month/Year navigation
            with ui.row().classes('w-full justify-between items-center mb-4'):
                ui.button('←', on_click=lambda: change_month(-1)).props('flat dense')
                month_label = ui.label(f'{datetime(current_year, current_month, 1).strftime("%B %Y")}').classes(
                    'text-2xl font-semibold')
                ui.button('→', on_click=lambda: change_month(1)).props('flat dense')

            # Weekday headers
            with ui.row().classes('w-full gap-1 sm:gap-2'):
                for day in ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']:
                    ui.label(day).classes('flex-1 text-center font-bold text-xs sm:text-base')

            # Calendar grid
            first_day, num_days = monthrange(current_year, current_month)
            day_num = 1

            # Create weeks
            for week in range(6):
                with ui.row().classes('w-full gap-1 sm:gap-2'):
                    for weekday in range(7):
                        # Empty cells before first day
                        if week == 0 and weekday < first_day:
                            ui.label('').classes('flex-1 h-16 sm:h-20 md:h-24')
                        # Empty cells after last day
                        elif day_num > num_days:
                            ui.label('').classes('flex-1 h-16 sm:h-20 md:h-24')
                        # Actual day cells
                        else:
                            day_date = date(current_year, current_month, day_num)
                            day_str = day_date.isoformat()
                            workout_count = workout_counts.get(day_str, 0)

                            # Determine styling based on workout count
                            is_today = day_date == today
                            card_classes = 'flex-1 h-16 sm:h-20 md:h-24 cursor-pointer hover:bg-blue-100 p-1 sm:p-2'

                            if is_today:
                                card_classes += ' border-2 border-blue-500'

                            if workout_count > 0:
                                card_classes += ' bg-green-100'

                            with ui.card().classes(card_classes).on('click', lambda d=day_str: ui.navigate.to(
                                    f'/day/{d}')):
                                ui.label(str(day_num)).classes('text-sm sm:text-base md:text-lg font-semibold')
                                if workout_count > 0:
                                    ui.label(f'{workout_count}').classes('text-xs text-green-700')

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

            app.storage.user['current_month'] = current_month
            app.storage.user['current_year'] = current_year
            ui.navigate.reload()

        create_calendar()

        # Quick navigation to today and progression
        with ui.row().classes('w-full justify-center gap-4 mt-6'):
            ui.button('Go to Today', on_click=lambda: ui.navigate.to(f'/day/{today.isoformat()}')).props(
                'color=primary')
            ui.button('View Progression', on_click=lambda: ui.navigate.to('/progression')).props(
                'color=secondary')


@ui.page('/day/{selected_date}')
def workout_session_view(selected_date: str):
    """Workout session view for a specific day."""
    ui.page_title(f'Workouts - {selected_date}')
    ui.dark_mode().enable()

    with ui.card().classes('w-full max-w-4xl mx-auto mt-8 p-6'):
        # Header with navigation
        with ui.row().classes('w-full justify-between items-center mb-6'):
            ui.button('← Back to Calendar', on_click=lambda: ui.navigate.to('/')).props('flat')
            ui.label(f'Workouts for {selected_date}').classes('text-2xl font-bold')

        # Load existing workouts for this day
        existing_workouts = workout_data.read_workouts_by_date(selected_date)

        # Display existing workouts
        if existing_workouts:
            ui.label('Today\'s Workouts (click to edit):').classes('text-xl font-semibold mt-4 mb-2')

            # Add indicator column for optional fields
            for workout in existing_workouts:
                has_optional = bool(workout.get('Distance') or workout.get('Time') or workout.get('Comment'))
                workout['_indicator'] = '💬' if has_optional else ''

            workout_table = ui.table(
                columns=[
                    {'name': 'exercise', 'label': 'Exercise', 'field': 'Exercise', 'align': 'left'},
                    {'name': 'category', 'label': 'Category', 'field': 'Category', 'align': 'left'},
                    {'name': 'weight', 'label': 'Weight', 'field': 'Weight', 'align': 'left'},
                    {'name': 'weight_unit', 'label': 'Unit', 'field': 'Weight Unit', 'align': 'left'},
                    {'name': 'reps', 'label': 'Reps', 'field': 'Reps', 'align': 'left'},
                    {'name': '_indicator', 'label': '', 'field': '_indicator', 'align': 'center'},
                ],
                rows=existing_workouts,
                row_key='Exercise'
            ).classes('w-full mb-2')

            # Container for clear button (will be populated after form inputs are created)
            clear_button_container = ui.row().classes('w-full justify-end mb-4')
        else:
            ui.label('No workouts logged for this day yet.').classes('text-gray-500 italic mb-2')

            # Button to add upcoming workout
            def add_upcoming_workout():
                """Add the next upcoming workout session to this day."""
                count = workout_data.pop_upcoming_workout_session(selected_date)
                if count > 0:
                    ui.navigate.reload()
                else:
                    ui.notify('No upcoming workouts available', type='warning')

            ui.button('Add Upcoming Workout', on_click=add_upcoming_workout).props('color=secondary').classes('mb-4')

            workout_table = None
            clear_button_container = None

        # Divider
        ui.separator().classes('my-6')

        # Form to add new workout
        ui.label('Workout Log').classes('text-xl font-semibold mb-4')

        # Track editing state
        editing_workout = {'original': None, 'is_editing': False}

        # Get all exercises grouped by category
        exercises_by_category = workout_data.get_exercises_by_category()
        categories = workout_data.get_categories()

        # Category selection (first field)
        category_options = ['➕ Add new category'] + categories
        category_select = ui.select(
            options=category_options,
            label='Category',
            value=None
        ).classes('w-full')

        # Custom category input (hidden by default)
        new_category_input = ui.input(
            label='New Category Name',
            placeholder='e.g., Chest, Back, Legs'
        ).classes('w-full')
        new_category_input.visible = False

        # Exercise selection (second field)
        exercise_select = ui.select(
            options=[],
            label='Exercise',
            value=None
        ).classes('w-full')

        # Custom exercise input (hidden by default)
        new_exercise_input = ui.input(
            label='New Exercise Name',
            placeholder='e.g., Flat Barbell Bench Press'
        ).classes('w-full')
        new_exercise_input.visible = False

        def update_exercise_options():
            """Update exercise dropdown based on selected category."""
            if category_select.value == '➕ Add new category':
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
                exercise_opts = ['➕ Add new exercise'] + exercises
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
            if exercise_select.value == '➕ Add new exercise':
                # Show new exercise input
                new_exercise_input.visible = True
                new_exercise_input.value = ''
            else:
                # Hide new exercise input
                new_exercise_input.visible = False

        category_select.on('update:model-value', on_category_change)
        exercise_select.on('update:model-value', on_exercise_change)

        with ui.row().classes('w-full gap-2'):
            weight_input = ui.number(label='Weight', placeholder='0.0', format='%.1f').classes('flex-1')
            weight_unit_input = ui.select(
                options=['lbs', 'kg'],
                label='Weight Unit',
                value='lbs'
            ).classes('flex-1')

        reps_input = ui.number(label='Reps', placeholder='0', format='%d').classes('w-full')

        # Toggle for optional fields
        show_optional = ui.checkbox('Show optional fields (Distance, Time, Comment)').classes('mt-4 mb-2')

        # Optional fields container (hidden by default)
        with ui.column().classes('w-full gap-4').bind_visibility_from(show_optional, 'value') as optional_container:
            with ui.row().classes('w-full gap-2'):
                distance_input = ui.number(label='Distance (optional)', placeholder='0.0', format='%.2f').classes('flex-1')
                distance_unit_input = ui.select(
                    options=['miles', 'km', 'meters', 'yards'],
                    label='Distance Unit',
                    value='miles'
                ).classes('flex-1')

            time_input = ui.input(label='Time (optional)', placeholder='e.g., 00:30:00').classes('w-full')
            comment_input = ui.textarea(label='Comment (optional)', placeholder='Notes about this set').classes('w-full')

        # Status message
        status_label = ui.label('').classes('text-green-600')

        def populate_form(workout_row):
            """Populate form with workout data from a table row."""
            # Store original workout for editing (remove UI-only fields)
            original = workout_row.copy()
            original.pop('_indicator', None)  # Remove indicator field added for UI
            editing_workout['original'] = original
            editing_workout['is_editing'] = True

            category = workout_row['Category']
            exercise = workout_row['Exercise']

            # Set category
            if category in categories:
                category_select.value = category
                new_category_input.visible = False
            else:
                category_select.value = '➕ Add new category'
                new_category_input.visible = True
                new_category_input.value = category

            # Update exercise options based on category
            update_exercise_options()

            # Set exercise
            if category in exercises_by_category and exercise in exercises_by_category[category]:
                exercise_select.value = exercise
                new_exercise_input.visible = False
            else:
                exercise_select.value = '➕ Add new exercise'
                new_exercise_input.visible = True
                new_exercise_input.value = exercise

            weight_input.value = float(workout_row['Weight']) if workout_row['Weight'] else None
            weight_unit_input.value = workout_row['Weight Unit'] if workout_row['Weight Unit'] else 'lbs'
            reps_input.value = int(workout_row['Reps']) if workout_row['Reps'] else None
            distance_input.value = float(workout_row['Distance']) if workout_row['Distance'] else None
            distance_unit_input.value = workout_row['Distance Unit'] if workout_row['Distance Unit'] else 'miles'
            time_input.value = workout_row['Time'] if workout_row['Time'] else ''
            comment_input.value = workout_row['Comment'] if workout_row['Comment'] else ''

            # Show optional fields if any of them have data
            if workout_row['Distance'] or workout_row['Time'] or workout_row['Comment']:
                show_optional.value = True

            # Switch to edit mode buttons
            create_button.visible = False
            edit_buttons_row.visible = True
            status_label.text = 'Editing workout - choose New Entry, Update, or Delete'
            status_label.classes('text-blue-600')

        def clear_form():
            """Clear all form fields and reset to blank state."""
            # Reset editing state
            editing_workout['original'] = None
            editing_workout['is_editing'] = False

            category_select.value = None
            new_category_input.value = ''
            new_category_input.visible = False
            exercise_select.value = None
            exercise_select.options = []
            new_exercise_input.value = ''
            new_exercise_input.visible = False
            weight_input.value = None
            weight_unit_input.value = 'lbs'
            reps_input.value = None
            distance_input.value = None
            distance_unit_input.value = 'miles'
            time_input.value = ''
            comment_input.value = ''
            show_optional.value = False

            # Switch to create mode buttons
            create_button.visible = True
            edit_buttons_row.visible = False
            status_label.text = ''

        # Make table rows clickable and add clear button if there are existing workouts
        if existing_workouts:
            workout_table.on('rowClick', lambda e: populate_form(e.args[1]))

            # Add clear button to the container created earlier
            with clear_button_container:
                ui.button('Add New Entry', on_click=clear_form).props('flat color=primary')

        def get_current_workout_data():
            """Get workout data from current form values."""
            # Determine category name
            if category_select.value == '➕ Add new category':
                category_name = new_category_input.value
            else:
                category_name = category_select.value

            # Determine exercise name
            if exercise_select.value == '➕ Add new exercise':
                exercise_name = new_exercise_input.value
            else:
                exercise_name = exercise_select.value

            return {
                'Date': selected_date,
                'Exercise': exercise_name,
                'Category': category_name,
                'Weight': weight_input.value if weight_input.value else '',
                'Weight Unit': weight_unit_input.value,
                'Reps': int(reps_input.value) if reps_input.value else '',
                'Distance': distance_input.value if distance_input.value else '',
                'Distance Unit': distance_unit_input.value if distance_input.value else '',
                'Time': time_input.value if time_input.value else '',
                'Comment': comment_input.value.replace('"', '""') if comment_input.value else ''
            }

        def update_table():
            """Refresh the workout table."""
            if existing_workouts is not None and workout_table is not None:
                updated_workouts = workout_data.read_workouts_by_date(selected_date)
                # Add indicator column for optional fields
                for workout_row in updated_workouts:
                    has_optional = bool(workout_row.get('Distance') or workout_row.get('Time') or workout_row.get('Comment'))
                    workout_row['_indicator'] = '💬' if has_optional else ''
                workout_table.rows = updated_workouts
                workout_table.update()

        def save_workout():
            """Create a new workout entry."""
            workout = get_current_workout_data()

            if not workout['Exercise'] or not workout['Category']:
                status_label.text = 'Error: Exercise and Category are required!'
                status_label.classes('text-red-600')
                return

            workout_data.write_workout(workout)

            # Only clear optional fields (keep category, exercise, weight, reps for next set)
            distance_input.value = None
            time_input.value = ''
            comment_input.value = ''

            update_table()

            status_label.text = 'Set logged! Add another set or change exercise.'
            status_label.classes('text-green-600')

        def update_workout_handler():
            """Update the existing workout being edited."""
            if not editing_workout['is_editing'] or not editing_workout['original']:
                return

            workout = get_current_workout_data()

            if not workout['Exercise'] or not workout['Category']:
                status_label.text = 'Error: Exercise and Category are required!'
                status_label.classes('text-red-600')
                return

            workout_data.update_workout(editing_workout['original'], workout)

            # Reset to create mode
            editing_workout['original'] = None
            editing_workout['is_editing'] = False
            create_button.visible = True
            edit_buttons_row.visible = False

            # Clear optional fields
            distance_input.value = None
            time_input.value = ''
            comment_input.value = ''

            update_table()

            status_label.text = 'Workout updated successfully!'
            status_label.classes('text-green-600')

        def delete_workout_handler():
            """Delete the current workout being edited."""
            if not editing_workout['is_editing'] or not editing_workout['original']:
                return

            workout_data.delete_workout(editing_workout['original'])

            # Clear form and reset state
            clear_form()

            update_table()

            status_label.text = 'Workout deleted successfully!'
            status_label.classes('text-green-600')

        # Buttons - different sets for create vs edit mode
        button_container = ui.row().classes('mt-4 gap-2')

        with button_container:
            # Create mode button (default)
            create_button = ui.button('Log Workout', on_click=save_workout).props('color=primary')

            # Edit mode buttons (hidden by default)
            with ui.row().classes('gap-2') as edit_buttons_row:
                new_entry_button = ui.button('New Entry', on_click=save_workout).props('color=primary')
                update_button = ui.button('Update', on_click=lambda: update_workout_handler()).props('color=positive')
                delete_button = ui.button('Delete', on_click=delete_workout_handler).props('color=negative')

            edit_buttons_row.visible = False


@ui.page('/progression')
def progression_view():
    """Progression tracking view showing historical and upcoming workouts."""
    ui.page_title('Progression Tracker')
    ui.dark_mode().enable()

    with ui.card().classes('w-full max-w-7xl mx-auto mt-8 p-6'):
        # Header with navigation
        with ui.row().classes('w-full justify-between items-center mb-6'):
            ui.button('← Back to Calendar', on_click=lambda: ui.navigate.to('/')).props('flat')
            ui.label('Progression Tracker').classes('text-3xl font-bold')

        # Exercise selection dropdown
        main_lifts = workout_data.get_main_lifts()
        selected_exercise = {'value': main_lifts[0] if main_lifts else None}

        def on_exercise_change(e):
            """Handle exercise selection change."""
            selected_exercise['value'] = e.value
            update_progression_view()

        # Exercise dropdown at the top
        with ui.row().classes('w-full mb-6'):
            ui.select(
                options=main_lifts,
                label='Select Exercise',
                value=selected_exercise['value'],
                on_change=on_exercise_change
            ).classes('w-64')

        # Container for chart and table
        chart_container = ui.column().classes('w-full')
        table_container = ui.column().classes('w-full mt-8')

        def update_progression_view():
            """Update the chart and table based on selected exercise."""
            chart_container.clear()
            table_container.clear()

            if not selected_exercise['value']:
                with chart_container:
                    ui.label('Please select an exercise').classes('text-gray-500 italic')
                return

            # Get progression data
            data = workout_data.get_progression_data(selected_exercise['value'])
            historical = data['historical']
            upcoming = data['upcoming']

            # Create chart
            with chart_container:
                if not historical and not upcoming:
                    ui.label(f'No data available for {selected_exercise["value"]}').classes('text-gray-500 italic')
                else:
                    # Prepare historical data
                    hist_dates = []
                    hist_estimated_1rm = []
                    hist_labels = []

                    for i, workout in enumerate(historical):
                        hist_dates.append(workout.get('Date', ''))
                        estimated_1rm = workout.get('estimated_1rm', 0)
                        hist_estimated_1rm.append(estimated_1rm)
                        weight = workout.get('Weight', '')
                        reps = workout.get('Reps', '')
                        hist_labels.append(f"{weight} lbs x {reps}<br>Est 1RM: {estimated_1rm:.1f} lbs")

                    # Prepare upcoming data - use projected dates
                    future_dates = []
                    future_estimated_1rm = []
                    future_labels = []

                    for i, workout in enumerate(upcoming):
                        projected_date = workout.get('projected_date', '')
                        future_dates.append(projected_date)
                        estimated_1rm = workout.get('estimated_1rm', 0)
                        future_estimated_1rm.append(estimated_1rm)
                        weight = workout.get('Weight', '')
                        reps = workout.get('Reps', '')
                        future_labels.append(f"{weight} lbs x {reps}<br>Est 1RM: {estimated_1rm:.1f} lbs")

                    # Create plotly figure
                    fig = go.Figure()

                    # Add historical data
                    if hist_estimated_1rm:
                        fig.add_trace(go.Scatter(
                            x=hist_dates,
                            y=hist_estimated_1rm,
                            mode='lines+markers',
                            name='Past Workouts',
                            line=dict(color='#4CAF50', width=2),
                            marker=dict(size=8, symbol='circle'),
                            text=hist_labels,
                            hovertemplate='<b>%{x}</b><br>%{text}<extra></extra>'
                        ))

                    # Add upcoming data with projected dates
                    if future_estimated_1rm:
                        fig.add_trace(go.Scatter(
                            x=future_dates,
                            y=future_estimated_1rm,
                            mode='lines+markers',
                            name='Future Workouts (Projected)',
                            line=dict(color='#2196F3', width=2),
                            marker=dict(size=8, symbol='circle'),
                            text=future_labels,
                            hovertemplate='<b>%{x}</b><br>%{text}<extra></extra>'
                        ))

                    # Calculate moving average trendline for all data (past + future)
                    if hist_estimated_1rm or future_estimated_1rm:
                        try:
                            import numpy as np

                            # Combine historical and future data
                            all_dates = hist_dates + future_dates
                            all_values = hist_estimated_1rm + future_estimated_1rm

                            if len(all_values) >= 3:
                                # Calculate moving average with window size of 5 (or less if not enough data)
                                window_size = min(5, len(all_values))
                                moving_avg = []

                                for i in range(len(all_values)):
                                    # Get window around current point
                                    start_idx = max(0, i - window_size // 2)
                                    end_idx = min(len(all_values), i + window_size // 2 + 1)
                                    window = all_values[start_idx:end_idx]
                                    moving_avg.append(np.mean(window))

                                fig.add_trace(go.Scatter(
                                    x=all_dates,
                                    y=moving_avg,
                                    mode='lines',
                                    name='Moving Average',
                                    line=dict(color='#FFD700', width=3),
                                    hovertemplate='<b>MA:</b> %{y:.1f} lbs<extra></extra>'
                                ))
                        except (ImportError, ValueError, TypeError):
                            pass  # Skip trendline if numpy not available or data issues

                        # Add vertical line to mark transition from past to future
                        if hist_dates and future_dates:
                            # Add a vertical line at the last historical date
                            from datetime import datetime as dt, timedelta
                            last_hist_date = hist_dates[-1]
                            first_future_date = future_dates[0]

                            # Calculate midpoint for the vertical line
                            try:
                                last_dt = dt.fromisoformat(last_hist_date)
                                first_ft = dt.fromisoformat(first_future_date)
                                midpoint = last_dt + (first_ft - last_dt) / 2

                                fig.add_vline(
                                    x=midpoint.isoformat()[:10],
                                    line_width=2,
                                    line_color="yellow",
                                    annotation_text="Today",
                                    annotation_position="top"
                                )
                            except (ValueError, TypeError):
                                pass

                    # Add range slider and selector buttons for different time scales
                    fig.update_xaxes(
                        rangeslider_visible=True,
                        rangeselector=dict(
                            buttons=list([
                                dict(count=1, label="1m", step="month", stepmode="backward"),
                                dict(count=3, label="3m", step="month", stepmode="backward"),
                                dict(count=6, label="6m", step="month", stepmode="backward"),
                                dict(count=1, label="1y", step="year", stepmode="backward"),
                                dict(step="all", label="All")
                            ]),
                            bgcolor="#1e1e1e",
                            activecolor="#2196F3",
                            x=0,
                            y=1.1
                        )
                    )

                    fig.update_layout(
                        xaxis_title='Date',
                        yaxis_title='Estimated 1RM (lbs)',
                        hovermode='closest',
                        showlegend=True,
                        height=650,
                        template='plotly_dark',
                        xaxis=dict(
                            rangeselector=dict(font=dict(color='white')),
                            type='date'
                        ),
                        dragmode='zoom'
                    )

                    ui.plotly(fig).classes('w-full')

            # Create tables
            with table_container:
                ui.label('Training Log Details').classes('text-2xl font-bold mb-4')

                # Historical workouts table
                if historical:
                    ui.label('Past Workouts (Best Set Per Day)').classes('text-xl font-semibold mt-4 mb-2')
                    hist_table_data = []
                    for workout in historical:
                        estimated_1rm = workout.get('estimated_1rm', 0)
                        hist_table_data.append({
                            'Date': workout.get('Date', ''),
                            'Weight': workout.get('Weight', ''),
                            'Unit': workout.get('Weight Unit', ''),
                            'Reps': workout.get('Reps', ''),
                            'Est 1RM': f"{estimated_1rm:.1f}",
                            'Comment': workout.get('Comment', '')
                        })

                    ui.table(
                        columns=[
                            {'name': 'date', 'label': 'Date', 'field': 'Date', 'align': 'left'},
                            {'name': 'weight', 'label': 'Weight', 'field': 'Weight', 'align': 'left'},
                            {'name': 'unit', 'label': 'Unit', 'field': 'Unit', 'align': 'left'},
                            {'name': 'reps', 'label': 'Reps', 'field': 'Reps', 'align': 'left'},
                            {'name': 'est_1rm', 'label': 'Est 1RM', 'field': 'Est 1RM', 'align': 'left'},
                            {'name': 'comment', 'label': 'Comment', 'field': 'Comment', 'align': 'left'},
                        ],
                        rows=hist_table_data,
                        row_key='Date',
                        pagination={'rowsPerPage': 10, 'sortBy': 'date', 'descending': True}
                    ).classes('w-full').props('rows-per-page-options="[10, 25, 50, 0]"')
                else:
                    ui.label('No past workouts logged yet').classes('text-gray-500 italic mt-4')

                # Upcoming workouts table
                if upcoming:
                    ui.label('Future Workouts (Best Set Per Session)').classes('text-xl font-semibold mt-6 mb-2')
                    future_table_data = []
                    for workout in upcoming:
                        estimated_1rm = workout.get('estimated_1rm', 0)
                        future_table_data.append({
                            'Projected Date': workout.get('projected_date', ''),
                            'Session': workout.get('Session', ''),
                            'Weight': workout.get('Weight', ''),
                            'Unit': workout.get('Weight Unit', ''),
                            'Reps': workout.get('Reps', ''),
                            'Est 1RM': f"{estimated_1rm:.1f}",
                            'Comment': workout.get('Comment', '')
                        })

                    ui.table(
                        columns=[
                            {'name': 'projected_date', 'label': 'Projected Date', 'field': 'Projected Date', 'align': 'left'},
                            {'name': 'session', 'label': 'Session', 'field': 'Session', 'align': 'left'},
                            {'name': 'weight', 'label': 'Weight', 'field': 'Weight', 'align': 'left'},
                            {'name': 'unit', 'label': 'Unit', 'field': 'Unit', 'align': 'left'},
                            {'name': 'reps', 'label': 'Reps', 'field': 'Reps', 'align': 'left'},
                            {'name': 'est_1rm', 'label': 'Est 1RM', 'field': 'Est 1RM', 'align': 'left'},
                            {'name': 'comment', 'label': 'Comment', 'field': 'Comment', 'align': 'left'},
                        ],
                        rows=future_table_data,
                        row_key='Session',
                        pagination={'rowsPerPage': 10, 'sortBy': 'projected_date', 'descending': False}
                    ).classes('w-full').props('rows-per-page-options="[10, 25, 50, 0]"')
                else:
                    ui.label('No upcoming workouts planned').classes('text-gray-500 italic mt-6')

        # Initial load
        update_progression_view()


# Run the app
ui.run(title='Workout Tracker', port=8080, reload=True, host='0.0.0.0', storage_secret='fitniz-secret-key-2024')
