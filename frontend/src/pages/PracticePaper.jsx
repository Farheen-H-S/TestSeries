import { useParams } from 'react-router-dom';

const PracticePaper = () => {
  const { paperId } = useParams();

  return (
    <div className="container">
      <h2>Practice Paper</h2>
      <p style={{ marginTop: '1rem', color: 'var(--text-secondary)' }}>
        Displaying Generated Practice Paper #{paperId}...
      </p>
    </div>
  );
};

export default PracticePaper;
