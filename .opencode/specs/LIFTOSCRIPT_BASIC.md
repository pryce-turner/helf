Basics
Each exercise goes on a separate line. It consists of sections separated by a slash (/). First goes the exercise name, and then in any order - the sections. The simplest exercise is written like this:

Bench Press / 3x8
You can do rep ranges too:

Bench Press / 3x8-12
You can list multiple sets, separated by commas, like this:

Bench Press / 1x5, 1x3, 1x1, 5x5
That would be 8 sets total - first 5 reps, then 3 reps, 1 rep, and then 5 sets of 5 reps.

If you don't specify the weight, it'll use the weight calculated from RPE tables, like this one. By default it'll assume you want to do exercises til failure (@10 RPE), so e.g. if you write:

Bench Press / 3x12
It'll check in the RPE table that for if you want to do 12 reps til failure (@10 RPE), you probably should use 65% of 1RM, so it'll set the weight to 65% of 1RM under the hood. If you don't want to go to full failure, you can specify desired RPE:

Bench Press / 3x12 @8
Then the weight would be lower - 60%. You can specify the weight explicitly, as a percentage of 1RM, like this:

Bench Press / 3x12 80%
Or you can specify the weight in kg/lb, like this:

Bench Press / 3x12 60kg
RPE, percentage and weight can be specified for each set or range of sets individually, so you can mix and match:

Bench Press / 1x5 @8, 1x3 @9, 1x1 @10, 5x5 50%
You can specify the rest time. E.g. this is how you could do myo-reps - i.e. doing heavy 12, and then doing 5x5 with short rest times and same weight:

Bench Press / 1x12 20s 60%, 5x5 20s 60%
You can also specify the rest time, weight, 1RM percentage and RPE also, for all sets, so you don't have to repeat yourself. Do it in a separate section like this:

Bench Press / 1x12, 5x5 / 20s 60%
To add AMRAP sets, add + after the reps number. And to log RPE, add + after the RPE number. Like this:

Bench Press / 4x5, 1x5+ @8+
If you want to enable "Quick add sets" feature (where you may have more sets than you planned), add + after the set number:

Bench Press / 3+x5
And if you want the app to ask you what was the weight you did (similar to AMRAP reps), you can add + after the weight:

Bench Press / 3x8 / 100lb+
or

Bench Press / 1x6 70%+, 5x5 50%
An example workout may look something like this:

Bench Press / 3x5 80%
Incline Bench Press / 3x8-12 @8 / 90s
Skullcrusher / 3x15 @8
Lateral Raise / 3x15 @8
By default, it'll use the default equipment - e.g. for Bench Press it'll use Barbell. If you want to specify a different equipment, then add it after the exercise name, like this:

Bench Press, Dumbbell / 3x5