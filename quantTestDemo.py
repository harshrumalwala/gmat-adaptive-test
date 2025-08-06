import random
import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from pulp import LpProblem, LpMaximize, LpVariable, lpSum, LpBinary, PulpSolverError

st.set_page_config(page_title="GMAT Adaptive Test Generator", layout="wide")
st.title("GMAT Adaptive Quant Test (MIP-Driven)")

st.markdown("""
This demo simulates a GMAT Focus-style **adaptive Quant test** using a **cell-based item pool** and **Mixed Integer Programming (MIP)** to select batches of questions dynamically based on performance.
""")

# ------------------------
# Step 1: Setup Dummy Multi-Cell Bank (Quant Only)
# ------------------------
cell_bank = []
topics = ["Algebra", "Coordinate Geometry", "Word Problems", "Arithmetic", "Combinations", "Probability", "Fraction", "Distance and Speed"]
difficulties = [1, 2, 3, 4, 5]
cell_id = 0

for topic in topics:
    for i in range(20):  # 20 cells per topic
        for j in range(5):  # 5 questions per cell
            cell_bank.append({
                "id": f"{topic[0]}C{cell_id}Q{j}",
                "topic": topic,
                "cell": f"{topic[0]}C{cell_id}",
                "question": f"[{topic}] Cell {cell_id} Q{j}: Dummy question text?",
                "difficulty": random.choice(difficulties),
                "answer": "A",
                "used": random.randint(0, 2),
                "time": random.choice([1.5, 2.0, 2.5])
            })
        cell_id += 1

questions_df = pd.DataFrame(cell_bank)

# ------------------------
# Session State Setup
# ------------------------
if "block_index" not in st.session_state:
    st.session_state.block_index = 0
    st.session_state.ability = 0
    st.session_state.blocks = []
    st.session_state.history = []
    st.session_state.topic_counts = {t: 0 for t in topics}
    st.session_state.prev_cells = []
    st.session_state.attempted_qids = set()

# ------------------------
# Function to Assemble a Batch using MIP
# ------------------------
def generate_batch(df, target_difficulty, num_questions=3):
    from collections import defaultdict
    max_attempts = 5
    base_margin = 2

    for attempt in range(max_attempts):
        margin = base_margin + attempt

        excluded_ids = st.session_state.attempted_qids
        df_filtered = df[~df.id.isin(excluded_ids)]

        model = LpProblem("Adaptive_Quant_Block", LpMaximize)
        x = {qid: LpVariable(f"x_{qid}", cat=LpBinary) for qid in df_filtered.id}

        topic_lookup = {qid: df_filtered[df_filtered.id == qid].topic.values[0] for qid in df_filtered.id}
        topic_counts = st.session_state.topic_counts

        model += lpSum([
            ((3 - df_filtered[df_filtered.id == qid].used.values[0]) + 
             (2.0 / (1 + topic_counts[topic_lookup[qid]]))) * x[qid]
            for qid in df_filtered.id
        ])

        model += lpSum([x[qid] for qid in df_filtered.id]) == num_questions
        model += lpSum([df_filtered[df_filtered.id == qid].difficulty.values[0] * x[qid] for qid in df_filtered.id]) <= target_difficulty * num_questions + margin
        model += lpSum([df_filtered[df_filtered.id == qid].difficulty.values[0] * x[qid] for qid in df_filtered.id]) >= max(target_difficulty * num_questions - margin, 1)

        for topic in df_filtered.topic.unique():
            topic_qids = [qid for qid in df_filtered.id if topic_lookup[qid] == topic]
            model += lpSum([x[qid] for qid in topic_qids]) <= 1

        recent_cells = st.session_state.prev_cells[-3:]
        model += lpSum([x[qid] for qid in df_filtered[df_filtered.cell.isin(recent_cells)].id]) == 0

        try:
            model.solve()
            selected = [qid for qid in x if x[qid].value() == 1]
            if selected:
                return df_filtered[df_filtered.id.isin(selected)]
        except PulpSolverError:
            continue

    return pd.DataFrame()

# ------------------------
# Step: Run Adaptive Blocks
# ------------------------
total_blocks = 7
questions_per_block = 3

if st.session_state.block_index < total_blocks:
    target = min(max(3 + st.session_state.ability, 1), 5)

    if len(st.session_state.blocks) <= st.session_state.block_index:
        block = generate_batch(questions_df, target, questions_per_block)
        if block.empty or len(block) < questions_per_block:
            st.warning("\u26a0\ufe0f Not enough suitable questions available. Please refresh or expand your pool.")
        st.session_state.blocks.append(block)
    else:
        block = st.session_state.blocks[st.session_state.block_index]

    st.markdown(f"### Block {st.session_state.block_index + 1} | Target Difficulty: {target}")
    user_answers = []
    for i, row in block.iterrows():
        st.write(f"{row['question']}")
        ans = st.text_input("Your Answer:", key=row['id'])
        user_answers.append((row['id'], ans, row['answer']))

    if st.button("Submit Block"):
        correct_count = 0
        for qid, ua, ca in user_answers:
            correct = ua.strip().lower() in ca.lower()
            topic = questions_df[questions_df.id == qid].topic.values[0]
            cell = questions_df[questions_df.id == qid].cell.values[0]
            st.session_state.history.append({
                "QID": qid,
                "Your Answer": ua,
                "Correct": correct,
                "Topic": topic,
                "Difficulty": questions_df[questions_df.id == qid].difficulty.values[0]
            })
            if correct:
                correct_count += 1
            st.session_state.topic_counts[topic] += 1
            st.session_state.prev_cells.append(cell)
            st.session_state.attempted_qids.add(qid)

        if correct_count >= questions_per_block * 0.8:
            st.session_state.ability += 1
        elif correct_count <= questions_per_block * 0.3:
            st.session_state.ability -= 1

        st.session_state.block_index += 1
        st.rerun()
else:
    st.success("Test Completed")
    hist = pd.DataFrame(st.session_state.history)
    st.dataframe(hist)

    st.markdown(f"**Final Accuracy:** {hist['Correct'].sum()}/{len(hist)}")
    st.markdown(f"**Avg Difficulty Faced:** {hist['Difficulty'].mean():.2f}")

    topic_dist = hist["Topic"].value_counts()
    st.bar_chart(topic_dist)

    st.subheader("Topic vs Difficulty Heatmap")
    heatmap_data = hist.groupby(["Topic", "Difficulty"]).size().unstack(fill_value=0)
    fig, ax = plt.subplots(figsize=(10, 4))
    sns.heatmap(heatmap_data, annot=True, cmap="YlGnBu", ax=ax)
    st.pyplot(fig)

    if st.button("Restart Test"):
        for key in ["block_index", "ability", "blocks", "history", "topic_counts", "prev_cells", "attempted_qids"]:
            del st.session_state[key]
        st.rerun()