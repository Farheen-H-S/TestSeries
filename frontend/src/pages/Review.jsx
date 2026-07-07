import { useParams } from 'react-router-dom';

const Review = () => {
  const { documentId } = useParams();

  return (
    <div className="container">
      <h2>Review Paper</h2>
      <p style={{ marginTop: '1rem', color: 'var(--text-secondary)' }}>
        Reviewing extracted questions for Document #{documentId}...
      </p>
    </div>
  );
};

export default Review;
